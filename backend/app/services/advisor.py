"""Generates advisor replies with the Google Gemini API."""

from flask import current_app
from google import genai
from google.genai import types

SYSTEM_PROMPT = """You are a financial education assistant for retail investors.
Explain investing concepts clearly, discuss diversification, risk, fees, and time horizon,
and relate your answers to the user's portfolio when it is provided.
You are not a licensed financial advisor: do not promise returns, and recommend that users
consult a licensed professional before making significant financial decisions."""


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
    lines = [f"- {h.symbol}: {h.quantity} shares at average cost {h.average_cost}" for h in portfolio.holdings]
    return "The user's current holdings:\n" + "\n".join(lines)


def generate_reply(messages, portfolio=None):
    """Return the model's reply to a conversation.

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

    try:
        response = _get_client().models.generate_content(
            model=current_app.config["GEMINI_MODEL"],
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_PROMPT}\n\n{_portfolio_context(portfolio)}",
                max_output_tokens=current_app.config["GEMINI_MAX_OUTPUT_TOKENS"],
            ),
        )
    except AdvisorUnavailableError:
        raise
    except Exception as err:
        current_app.logger.exception("Gemini request failed")
        raise AdvisorUnavailableError("The advisor service is unavailable") from err

    if not response.text:
        raise AdvisorUnavailableError("The advisor returned an empty response")
    if response.candidates and response.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
        current_app.logger.warning("Gemini reply hit GEMINI_MAX_OUTPUT_TOKENS and was cut off")
        return response.text + "\n\n*(This answer was cut off because it hit the length limit.)*"
    return response.text
