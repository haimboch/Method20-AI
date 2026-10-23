"""Optional OpenAI visual reading of the exact daily chart used in METHOD20 report.

Model commentary is non-authoritative: it must not alter computed signals.
Requires OPENAI_API_KEY secret. On errors, marks review unavailable.
"""
import os
import json
import base64
import requests

def review_chart(symbol, chart_path, numbers):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        return {"status":"NOT_CONFIGURED","text":"ניתוח AI חזותי טרם הופעל. יש להגדיר OPENAI_API_KEY ב-GitHub Secrets."}
    model=os.getenv("OPENAI_VISION_MODEL","gpt-4o-mini")
    with open(chart_path,"rb") as f:
        b64=base64.b64encode(f.read()).decode("ascii")
    prompt=(
        "You are an independent visual chart reviewer for METHOD 20. "
        "Respond in HEBREW, 80-130 words, plain text, no markdown. "
        "Inspect DAILY candlestick chart with ONLY SMA20, volume and CCI14. "
        "Comment on apparent buyer/seller balance, trend in last week/month, "
        "price vs SMA20, candle reversal clues, and uncertainties. "
        "Use the numeric data below to avoid guessing exact prices. "
        "NEVER invent gaps or dates; say when you cannot verify them from the image. "
        "DO NOT alter statuses or promise trades. No buy/sell orders. "
        "Explicitly distinguish what is visible from what is merely an interpretation. "
        "Numeric data: "+json.dumps(numbers,ensure_ascii=False,default=str)
    )
    payload={
        "model":model,
        "messages":[{"role":"user","content":[
            {"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":"data:image/png;base64,"+b64,"detail":"high"}}
        ]}],
        "max_tokens":450
    }
    try:
        r=requests.post("https://api.openai.com/v1/chat/completions",
                        headers={"Authorization":"Bearer "+key},
                        json=payload,timeout=90)
        r.raise_for_status()
        response=r.json()
        content=response["choices"][0]["message"]["content"]
        if not isinstance(content,str) or not content.strip():
            raise ValueError("Empty AI review")
        return {"status":"COMPLETE","text":content.strip(),"model":model}
    except Exception as exc:
        # Never put raw API exception payloads in the public report.
        return {"status":"UNAVAILABLE","text":"ניתוח AI לא זמין בהרצה זו. יש לבדוק את שלב הדוח והגדרות ה-API."}
