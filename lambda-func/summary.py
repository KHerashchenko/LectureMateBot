import os
from typing import Any, Dict

import openai
from pyrate_limiter import Duration, Limiter, RequestRate
import math
import tiktoken

# Constants
MAX_CHUNK_TOKEN_SIZE = 1000
MAX_TOKENS = 2049  # max number of token (note: text-curie-001 has a max of 2048)
GPT_MODEL = "text-curie-001"  # GPT-3 model to use
MAX_CHUNK_LENGTH = 2000

# Token bucket rate limiting parameters
RATE_LIMIT = 10  # max number of requests per minute
RATE_LIMIT_PERIOD = 60  # period in seconds


rate_limits = (RequestRate(10, Duration.MINUTE),)  # 10 requests a minute


# Create the rate limiter
# Pyrate Limiter instance
limiter = Limiter(*rate_limits)

def num_tokens_from_string(string: str, encoding_name: str = "gpt2") -> int:
    """
    Returns the number of tokens in a text string.
    https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def estimate_word_count(num_tokens: int) -> int:
    """
    Given the number of GPT-2 tokens, estimates the real word count.
    """
    # The average number of real words per token for GPT-2 is 0.56, according to OpenAI.
    # Multiply the number of tokens by this average to estimate the total number of real
    # words.
    return math.ceil(num_tokens * 0.56)


def load_text_file(filename: str) -> str:
    """
    Load a text file from the same directory as this script.
    """
    script_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_directory, filename)
    with open(file_path, "r", encoding="utf-8") as file:
        file_read_data = file.read()
    return file_read_data


def write_text_file(text: str, filename: str) -> str:
    """
    Write a text file from the same directory as this script.
    """
    script_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_directory, filename)

    with open(file_path, "w", encoding="utf-8") as output_file:
        output_file.write(text)

    return file_path


def recursive_summarization(
    summary_size: int, chunk_text: str, prefix_text: str = ""
) -> str:
    """
    Recursive summarization function.
    """
    summary_string = (
        f"```{prefix_text}```\n\n"
        + "new text:\n\n```"
        # + f"{estimate_word_count(max_token_length)} words:\n"
        + chunk_text
        + "```\n\nsummarize then append to last text, write close to [replace] "
        " words, use extractive summarization if you have too much text, use"
        " abstractive summarization (no gibberish) if you don't have enough:\n\n```"
    )

    summary_string = summary_string.replace(
        "[replace]", str(estimate_word_count(summary_size))
    )

    response: Dict[str, Any] = openai.Completion.create(  # type: ignore
        model=GPT_MODEL,
        prompt=summary_string,
        frequency_penalty=0.5,
        max_tokens=MAX_TOKENS
        - num_tokens_from_string(summary_string),  # eg 4000-(len chunk+len string)
    )

    if len(response) == 0:
        print("response=", response)  # error
        return "Error: unable to generate response."

    response_text = response["choices"][0]["text"]
    return response_text


def summarize_text(
    text: str, max_token_length: int, max_tokens: int = MAX_TOKENS
) -> str:
    """
    Summarize the prompt using GPT-3.
    """

    original_num_tokens = num_tokens_from_string(text)

    summary_size = max_token_length if max_token_length <= max_tokens else max_tokens

    chunks = [
        text[i : i + MAX_CHUNK_LENGTH] for i in range(0, len(text), MAX_CHUNK_LENGTH)
    ]
    result = ""
    summary = ""
    for chunk in chunks:
        print("chunk=", chunk)

        limiter.try_acquire("summarize_text")
        summary = recursive_summarization(summary_size, chunk, summary)
        result += summary

    num_tokens = num_tokens_from_string(result)
    print("num_tokens=", num_tokens, "original_num_tokens=", original_num_tokens)

    if num_tokens > max_token_length:
        # iterate again, EXPENSIVE try again
        print("dividing prompt")
        return summarize_text(result, max_token_length)

    return result


def cleanup_summary(text: str, summary_size: int, max_tokens: int = MAX_TOKENS) -> str:
    """
    Cleanup the summary using GPT-3.

    Args:
        text (str): The text to summarize.
        summary_size (int): The desired summary size in tokens.
        max_tokens (int): The maximum number of tokens to use.
    """

    summary_size = summary_size if summary_size <= max_tokens else max_tokens

    cleanup_prompt = (
        "cleanup this machine generated summarization, notably "
        + "in the ligatures between passages, write close to [replace] words, use"
        " extractive summarization if you have too much text, use abstractive"
        " summarization if you don't have enough, no gibberish or bad"
        f" formatting:\n```{text}```"
    )

    cleanup_prompt = cleanup_prompt.replace(
        "[replace]", str(estimate_word_count(summary_size))
    )

    response: Dict[str, Any] = openai.Completion.create(  # type: ignore
        model="text-davinci-003",
        prompt=cleanup_prompt,
        best_of=3,
        max_tokens=max_tokens - num_tokens_from_string(cleanup_prompt),
    )
    if len(response) == 0:
        print("response error=", response)  # error
        return "Error: unable to generate response."

    response_text = response["choices"][0]["text"]
    print("response_text=", response_text)
    return response_text

def summarize(text):
    SUMMARY_SIZE = 700
    output = summarize_text(text, SUMMARY_SIZE)
    return cleanup_summary(output, SUMMARY_SIZE)
