"""Generates advisor replies with the Google Gemini API."""

import time

from flask import current_app
from google import genai
from google.genai import errors, types

from app.services.quotes import get_quotes

SYSTEM_PROMPT = """You are a financial education assistant for retail investors.
Explain investing concepts clearly, discuss diversification, risk, fees, and time horizon,
and relate your answers to the user's portfolio when it is provided.
You are not a licensed financial advisor: do not promise returns, and recommend that users
consult a licensed professional before making significant financial decisions."""

TRUNCATION_NOTE = "\n\n*(This answer was cut off because it hit the length limit.)*"


class AdvisorUnavailableError(Exception):
    pass


# Gemini errors worth retrying: rate limits (429, common on free keys) and "model overloaded" or other 5xx errors.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _status_code(err):
    return err.code if isinstance(err, errors.APIError) else None


def _user_message(err):
    code = _status_code(err)
    if code == 429:
        return "The advisor is getting too many requests right now. Please wait a minute and try again."
    if code in RETRYABLE_STATUS_CODES:
        return "The advisor is temporarily overloaded. Please try again in a moment."
    return "The advisor service is unavailable"


def _should_retry(err, delays):
    if delays and _status_code(err) in RETRYABLE_STATUS_CODES:
        current_app.logger.warning("Gemini returned %s; retrying in %ss", _status_code(err), delays[0])
        time.sleep(delays.pop(0))
        return True
    return False


_client = None


def _get_client():
    global _client
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        raise AdvisorUnavailableError("GEMINI_API_KEY is not configured")
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client


def _portfolio_context(portfolio):
    if portfolio is None or not portfolio.holdings:
        return "The user has not entered any holdings."
    quotes = get_quotes([h.symbol for h in portfolio.holdings])
    lines = []
    for h in portfolio.holdings:
        line = f"- {h.symbol}: {h.quantity} shares at average cost {h.average_cost}"
        quote = quotes.get(h.symbol)
        if quote:
            line += f", current price {quote['price']} {quote['currency']}"
        lines.append(line)
    return "The user's current holdings:\n" + "\n".join(lines)


def build_request(messages, portfolio):
    """Build the generate_content arguments from plain data (no ORM objects are kept).

    `messages` is the conversation so far (objects with .role and .content, oldest first), ending with the
    user's new message. Call this while the request's database session is still open.
    """
    limit = current_app.config["CHAT_HISTORY_LIMIT"]
    contents = [
        types.Content(
            # Gemini calls the assistant role "model".
            role="model" if m.role == "assistant" else "user",
            parts=[types.Part.from_text(text=m.content)],
        )
        for m in messages[-limit:]
    ]
    return {
        "model": current_app.config["GEMINI_MODEL"],
        "contents": contents,
        "config": types.GenerateContentConfig(
            system_instruction=f"{SYSTEM_PROMPT}\n\n{_portfolio_context(portfolio)}",
            max_output_tokens=current_app.config["GEMINI_MAX_OUTPUT_TOKENS"],
        ),
    }


def _hit_token_limit(response):
    truncated = bool(response.candidates) and response.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS
    if truncated:
        current_app.logger.warning("Gemini reply hit GEMINI_MAX_OUTPUT_TOKENS and was cut off")
    return truncated


def generate_reply(messages, portfolio=None):
    """Return the model's full reply to a conversation."""
    request = build_request(messages, portfolio)
    delays = list(current_app.config["GEMINI_RETRY_DELAYS"])
    while True:
        try:
            response = _get_client().models.generate_content(**request)
            break
        except AdvisorUnavailableError:
            raise
        except Exception as err:
            if _should_retry(err, delays):
                continue
            current_app.logger.exception("Gemini request failed")
            raise AdvisorUnavailableError(_user_message(err)) from err

    if not response.text:
        raise AdvisorUnavailableError("The advisor returned an empty response")
    return response.text + (TRUNCATION_NOTE if _hit_token_limit(response) else "")


def stream_reply(request):
    """Yield the model's reply in text chunks as Gemini produces them.

    `request` comes from build_request(). Temporary Gemini errors are retried, but only before any text was
    yielded, since a retry can't take back what the user has already seen. Raises AdvisorUnavailableError
    (possibly after some chunks were yielded) if the request fails.
    """
    delays = list(current_app.config["GEMINI_RETRY_DELAYS"])
    while True:
        produced_text = False
        try:
            for chunk in _get_client().models.generate_content_stream(**request):
                if chunk.text:
                    produced_text = True
                    yield chunk.text
                if _hit_token_limit(chunk):
                    yield TRUNCATION_NOTE
            break
        except AdvisorUnavailableError:
            raise
        except Exception as err:
            if not produced_text and _should_retry(err, delays):
                continue
            current_app.logger.exception("Gemini streaming request failed")
            raise AdvisorUnavailableError(_user_message(err)) from err

    if not produced_text:
        raise AdvisorUnavailableError("The advisor returned an empty response")
