from openai import OpenAI
import time
import json
from Services.usage_logger import log_usage
from Services.order_service import SIPARIS_TOOL, SIPARIS_GUNCELLE_TOOL
from Services.ikas_service import URUN_ARA_TOOL
from config import (
    OPENAI_API_KEY,
    MODEL_NAME,
    INPUT_TOKEN_PRICE,
    OUTPUT_TOKEN_PRICE
)

client = OpenAI(
    api_key=OPENAI_API_KEY
)

def _create_chat(messages, sender, tools=None):

    start_time = time.time()

    # tools verilmişse modele tool calling imkanı tanınır
    if tools:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
    else:
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

    message = response.choices[0].message

    # Modelin döndürdüğü tool çağrısı varsa ilkini parse et
    tool_call = None

    if message.tool_calls:

        first_call = message.tool_calls[0]

        tool_call = {
            "name": first_call.function.name,
            "arguments": json.loads(first_call.function.arguments)
        }

    return {

        "answer": message.content,

        "tool_call": tool_call,

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

    # urun_ara tool'u ile müşteri ürünü isimle de sorabilir
    return _create_chat(
        messages,
        sender,
        tools=[URUN_ARA_TOOL]
    )

def product_chat(
    system_prompt,
    products_block,
    history,
    message_text,
    sender,
    include_order_tool=True,
    include_update_tool=False
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

    # urun_ara her zaman verilir (isimle ürün sorgusu link akışına ek).
    # siparis_olustur tool'u yalnızca yeni sipariş alınabilir durumda (order_state None) verilir.
    # Sipariş zaten oluşturulmuşsa onun yerine siparis_guncelle verilir; böylece müşteri
    # sonradan sipariş değişikliği (adres/ürün/renk/beden/adet/ödeme) isteyebilir.
    tools = [URUN_ARA_TOOL]

    if include_order_tool:
        tools.append(SIPARIS_TOOL)

    if include_update_tool:
        tools.append(SIPARIS_GUNCELLE_TOOL)

    return _create_chat(
        messages,
        sender,
        tools=tools
    )