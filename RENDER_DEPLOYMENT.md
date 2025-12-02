# הוראות פריסה ב-Render.com

## שלב 1: קבלת טוקן אימות

לפני הפריסה, צריך לקבל טוקן אימות תקף:

```bash
python gplay-downloader.py auth -r 50
```

הפקודה תנסה עד 50 פעמים לקבל טוקן תקף. כשהיא מצליחה, הטוקן נשמר ב-`~/.gplay-auth.json`

## שלב 2: העתקת הטוקן

העתק את כל התוכן של הקובץ `~/.gplay-auth.json` (זה JSON אחד ארוך).

ב-Windows:
```cmd
type %USERPROFILE%\.gplay-auth.json
```

ב-Linux/Mac:
```bash
cat ~/.gplay-auth.json
```

## שלב 3: הגדרת משתנה סביבה ב-Render

1. היכנס ל-Render Dashboard
2. בחר את השירות שלך
3. לך ל-**Environment** בתפריט הצד
4. לחץ על **Add Environment Variable**
5. הוסף:
   - **Key**: `GPLAY_AUTH_TOKEN`
   - **Value**: הדבק את כל תוכן הקובץ JSON (שורה אחת ארוכה)

## שלב 4: פריסה

Render יעשה deploy אוטומטי אחרי שתשמור את משתנה הסביבה.

## בדיקה

אחרי הפריסה, בדוק שהשרת עובד:

```bash
curl https://your-app.onrender.com/api/auth/status
```

אמור להחזיר:
```json
{"authenticated": true}
```

## פתרון בעיות

### השרת עדיין מקבל 403

1. ודא שהטוקן הועתק נכון (כולל כל הסוגריים והמרכאות)
2. נסה לקבל טוקן חדש עם יותר ניסיונות:
   ```bash
   python gplay-downloader.py auth -r 100
   ```
3. ודא שהטוקן עבר validation (צריך לראות "✓ Token validated successfully")

### הטוקן פג תוקף

טוקנים יכולים לפוג תוקף. אם זה קורה:
1. הרץ שוב `python gplay-downloader.py auth -r 50`
2. עדכן את משתנה הסביבה `GPLAY_AUTH_TOKEN` ב-Render
3. Render יעשה deploy אוטומטי

## הערות

- הטוקן הוא אנונימי ולא מכיל מידע אישי
- הטוקן מתקבל מ-AuroraOSS Dispenser
- לפעמים צריך כמה ניסיונות כדי לקבל טוקן טוב
- טוקנים טובים עוברים validation מול אפליקציות כמו Chase
