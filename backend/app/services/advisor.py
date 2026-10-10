"""Generates advisor replies with the Google Gemini API."""

from flask import current_app
from google import genai
from google.genai import types

from app.services.quotes import get_quotes

SYSTEM_PROMPT = """You are a financial education assistant for retail investors.
Explain investing concepts clearly, discuss diversification, risk, fees, and time horizon,
and relate your answers to the user's portfolio when it is provided.
You are not a licensed financial advisor: do not promise returns, and recommend that users
consult a licensed professional before making significant financial decisions."""

TRUNCATION_NOTE = "\n\n*(This answer was cut off because it hit the length limit.)*"


class AdvisorUnavailableError(Exception):
    pass


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


def _request_args(messages, portfolio):
    """Build the generate_content arguments.

    `messages` is the conversation so far (Message rows, oldest first), ending with the user's new message.
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
    try:
        response = _get_client().models.generate_content(**_request_args(messages, portfolio))
    except AdvisorUnavailableError:
        raise
    except Exception as err:
        current_app.logger.exception("Gemini request failed")
        raise AdvisorUnavailableError("The advisor service is unavailable") from err

    if not response.text:
        raise AdvisorUnavailableError("The advisor returned an empty response")
    return response.text + (TRUNCATION_NOTE if _hit_token_limit(response) else "")


def stream_reply(messages, portfolio=None):
    """Yield the model's reply in text chunks as Gemini produces them.

    Raises AdvisorUnavailableError (possibly after some chunks were yielded) if the request fails.
    """
    try:
        args = _request_args(messages, portfolio)
        produced_text = False
        for chunk in _get_client().models.generate_content_stream(**args):
            if chunk.text:
                produced_text = True
                yield chunk.text
            if _hit_token_limit(chunk):
                yield TRUNCATION_NOTE
    except AdvisorUnavailableError:
        raise
    except Exception as err:
        current_app.logger.exception("Gemini streaming request failed")
        raise AdvisorUnavailableError("The advisor service is unavailable") from err

    if not produced_text:
        raise AdvisorUnavailableError("The advisor returned an empty response")
