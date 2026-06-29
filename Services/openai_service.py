from openai import OpenAI
import time
from Services.usage_logger import log_usage
from config import (
    OPENAI_API_KEY,
    MODEL_NAME,
    INPUT_TOKEN_PRICE,
    OUTPUT_TOKEN_PRICE
)

client = OpenAI(
    api_key=OPENAI_API_KEY
)

def _create_chat(messages, sender):

    start_time = time.time()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages
    )

    response_time = time.time() - start_time
    prompt_cost = (
                          response.usage.prompt_tokens
                          / 1_000_000
                  ) * INPUT_TOKEN_PRICE

    completion_cost = (
                              response.usage.completion_tokens
                              / 1_000_000
                      ) * OUTPUT_TOKEN_PRICE

    total_cost = prompt_cost + completion_cost

    log_usage(

        sender=sender,

        model=MODEL_NAME,

        prompt_tokens=response.usage.prompt_tokens,

        completion_tokens=response.usage.completion_tokens,

        total_tokens=response.usage.total_tokens,

        cost=round(total_cost, 6),

        response_time=round(response_time, 3)

    )

    return {

        "answer": response.choices[0].message.content,

        "prompt_tokens": response.usage.prompt_tokens,

        "completion_tokens": response.usage.completion_tokens,

        "total_tokens": response.usage.total_tokens,

        "response_time": round(response_time, 3),

        "cost": round(total_cost, 6)

    }

def general_chat(
    general_prompt,
    message_text,
    sender
):

    messages = [

        {
            "role": "system",
            "content": general_prompt
        },

        {
            "role": "user",
            "content": message_text
        }

    ]

    return _create_chat(messages,
                        sender)

def product_chat(
    system_prompt,
    products_block,
    history,
    message_text,
    sender
):

    messages = [

        {
            "role": "system",
            "content":
                system_prompt
                + "\n\nÜrün Bilgileri:\n"
                + products_block
        },

        *history,

        {
            "role": "user",
            "content": message_text
        }

    ]

    return _create_chat(messages,sender)