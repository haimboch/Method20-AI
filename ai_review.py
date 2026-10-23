"""Optional image-based METHOD20 review. Never print keys or raw API errors."""
import os
import json
import base64
import requests

def review_chart(symbol, chart_path, numbers):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        return {"status":"NOT_CONFIGURED","text":"מפתח OPENAI_API_KEY לא הוגדר."}
    model=os.getenv("OPENAI_VISION_MODEL","gpt-4o-mini")
    with open(chart_path,"rb") as f:
        b64=base64.b64encode(f.read()).decode("ascii")
    prompt=(
        "Inspect this DAILY candlestick chart with SMA20, volume and CCI14. "
        "Respond in Hebrew, 80-130 words, plain text. Describe buyer/seller "
        "balance, recent trend, candlestick reversal clues, relative position "
        "to SMA20, volume and CCI. Separate visual observations from interpretation. "
        "Do not guess prices, gaps, dates or make trading instructions. "
        "Explain conditional support/resistance scenarios only if supported by provided levels; "
        "do not claim numerical probabilities or certainty. "
        "The quantitative rules and statuses are authoritative and cannot be "
        "overridden by this visual review. Facts: "
        +json.dumps(numbers,ensure_ascii=False,default=str)
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
        r=requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization":"Bearer "+key},
            json=payload,timeout=90
        )
        if not r.ok:
            error_code="unknown"
            try:
                value=r.json().get("error",{})
                candidate=value.get("code") or value.get("type") or "unknown"
                allowed={"insufficient_quota","rate_limit_exceeded",
                         "invalid_api_key","model_not_found","billing_hard_limit_reached",
                         "invalid_request_error","authentication_error",
                         "permission_error","server_error"}
                if candidate in allowed:
                    error_code=candidate
            except (ValueError, TypeError, AttributeError):
                pass
            category={
                400:"INVALID_REQUEST",401:"AUTH_ERROR",403:"PERMISSION_DENIED",
                404:"MODEL_NOT_FOUND",408:"REQUEST_TIMEOUT",
                429:"QUOTA_OR_RATE_LIMIT",500:"PROVIDER_ERROR",
                502:"PROVIDER_ERROR",503:"PROVIDER_ERROR"
            }.get(r.status_code,"HTTP_ERROR")
            print(f"AI_REVIEW_FAILED ticker={symbol} http={r.status_code} category={category} code={error_code}",flush=True)
            explanations={
                "AUTH_ERROR":"מפתח OpenAI לא תקין, בוטל או אינו מורשה.",
                "PERMISSION_DENIED":"אין לפרויקט הרשאה למודל או לשירות.",
                "MODEL_NOT_FOUND":"מודל ה-AI אינו זמין בחשבון זה.",
                "QUOTA_OR_RATE_LIMIT":"ייתכן שאין יתרה בחשבון ה-API או שהגעת למגבלת קצב.",
                "INVALID_REQUEST":"הבקשה נדחתה. בדוק תמיכת המודל בתמונות.",
                "PROVIDER_ERROR":"שגיאה זמנית בשירות OpenAI."
            }
            return {"status":"UNAVAILABLE","error_category":category,
                    "http_status":r.status_code,"error_code":error_code,
                    "text":explanations.get(category,"בקשת OpenAI נכשלה.")+
                           f" (HTTP {r.status_code}; code: {error_code})"}
        response=r.json()
        text=response["choices"][0]["message"]["content"]
        if not isinstance(text,str) or not text.strip():
            raise ValueError("Empty model response")
        print(f"AI_REVIEW_COMPLETE ticker={symbol}",flush=True)
        return {"status":"COMPLETE","text":text.strip(),"model":model}
    except requests.Timeout:
        print(f"AI_REVIEW_FAILED ticker={symbol} category=TIMEOUT",flush=True)
        return {"status":"UNAVAILABLE","error_category":"TIMEOUT",
                "text":"עבר זמן ההמתנה לשירות OpenAI."}
    except requests.RequestException:
        print(f"AI_REVIEW_FAILED ticker={symbol} category=NETWORK_ERROR",flush=True)
        return {"status":"UNAVAILABLE","error_category":"NETWORK_ERROR",
                "text":"תקלה בתקשורת עם שירות OpenAI."}
    except (ValueError,KeyError,IndexError,TypeError):
        print(f"AI_REVIEW_FAILED ticker={symbol} category=RESPONSE_FORMAT",flush=True)
        return {"status":"UNAVAILABLE","error_category":"RESPONSE_FORMAT",
                "text":"OpenAI החזיר תשובה ריקה או בפורמט בלתי צפוי."}
