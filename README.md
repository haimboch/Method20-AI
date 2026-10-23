# METHOD 20 AI

מערכת מחקר טכני יומית (LONG בלבד). **ללא פקודות מסחר**.

## פיילוט
SPCX, WDC, NBIS, IREN, MU. אינדיקטורים: **SMA20 בלבד**, CCI(14), Volume, נרות יפניים וגאפים.

## הרצה בענן (ללא התקנת Python)
1. ב-GitHub פתח Settings > Secrets and variables > Actions > New repository secret.
2. צור סוד בשם `MASSIVE_API_KEY` עם מפתח API אישי משלך. אין לשלוח את המפתח בצ'אט או להכניסו לקוד.
3. פתח Actions > METHOD 20 Manual Report > Run workflow.
4. לאחר ההרצה, הורד את ה-Artifact בשם `method20-html-report`, חלץ אותו ופתח `report.html` בדפדפן.

ההרצה **ידנית בלבד** בשלב זה; אין תזמון, אין דואר אלקטרוני ואין עדיין ניתוח גרפים באמצעות מודל AI חזותי. תוצאות זיהוי הסטאפים היוריסטיות ודורשות אימות אנושי. הדוח משתמש בנתוני Massive חיים דרך API עצמאי ומציין במפורש כששליפה נכשלת.

## כללי נר היפוך
נר היפוך הוא סימן READY בלבד. פריצת הגבוה בבר מאוחר יותר = TRIGGERED; שבירת הנמוך קודם = INVALIDATED. פריצת שניהם באותו נר OHLC = AMBIGUOUS. אין תפוגת זמן.
