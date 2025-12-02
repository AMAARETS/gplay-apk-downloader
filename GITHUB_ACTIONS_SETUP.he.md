# מדריך הגדרת GitHub Actions

## הבעיה: Dispenser חסום על ידי GitHub

כתובות IP של GitHub Actions לרוב חסומות על ידי ה-dispenser של AuroraOSS, מה שגורם לשגיאות 403 Forbidden.

## פתרונות

### אופציה 1: שימוש בטוקן ידני (מומלץ)

1. **קבל טוקן במחשב המקומי:**
   ```bash
   # במחשב שלך (לא ב-GitHub Actions)
   ./gplay auth --max-attempts 20
   ```

2. **העתק את הטוקן:**
   ```bash
   cat ~/.gplay-auth.json
   ```

3. **הוסף כ-Secret בגיטהאב:**
   - עבור למאגר שלך → Settings → Secrets and variables → Actions
   - לחץ "New repository secret"
   - שם: `GPLAY_AUTH_TOKEN`
   - ערך: הדבק את כל התוכן של `~/.gplay-auth.json`
   - לחץ "Add secret"

4. **הרץ את ה-workflow:**
   - ה-workflow ישתמש אוטומטית בטוקן שלך
   - הטוקן תקף למספר שבועות/חודשים

### אופציה 2: שימוש ב-Tor Proxy (ניסיוני)

ה-workflow כולל אופציה להשתמש ב-Tor proxy כדי לעקוף חסימות IP:

1. כשמריצים את ה-workflow, הגדר "Try using proxy" ל-`true`
2. זה ינתב את האימות דרך רשת Tor
3. עשוי להיות איטי יותר אבל יכול לעקוף חסימות IP

**הערה:** תמיכה ב-Tor דורשת את החבילה `pysocks` (כבר ב-requirements.txt)

### אופציה 3: Self-Hosted Runner

אם יש לך שרת/VPS שלא חסום:

1. הגדר [self-hosted GitHub Actions runner](https://docs.github.com/en/actions/hosting-your-own-runners)
2. שנה את ה-workflow להשתמש ב-runner שלך:
   ```yaml
   runs-on: self-hosted  # במקום ubuntu-latest
   ```

## תפוגת טוקן

טוקני אימות בסופו של דבר פגים. כשאתה רואה שגיאות אימות:

1. צור טוקן חדש במקומי: `./gplay auth --max-attempts 20`
2. עדכן את ה-secret `GPLAY_AUTH_TOKEN` בגיטהאב

## בדיקה מקומית

לפני שימוש ב-GitHub Actions, בדוק מקומית:

```bash
# אימות
./gplay auth --max-attempts 20

# בדיקת הורדה
./gplay download com.whatsapp -m -a arm64

# אם הצליח, אותו טוקן יעבוד ב-GitHub Actions
```

## פתרון בעיות

### "Authentication failed" ב-GitHub Actions

1. בדוק אם ה-secret `GPLAY_AUTH_TOKEN` מוגדר נכון
2. וודא שהטוקן תקף על ידי בדיקה מקומית
3. נסה ליצור מחדש את הטוקן

### "Token validation failed"

הטוקן עשוי להיות פג תוקף או לא תקין:
1. צור טוקן חדש במקומי
2. עדכן את ה-secret בגיטהאב

### Proxy לא עובד

אם Tor proxy נכשל:
1. כבה את אופציית ה-proxy (הגדר ל-`false`)
2. השתמש בטוקן ידני במקום (אופציה 1)

---

## התחלה מהירה

**הדרך הכי קלה להתחיל:**

```bash
# 1. במחשב המקומי שלך
./gplay auth --max-attempts 20

# 2. העתק את הטוקן
cat ~/.gplay-auth.json

# 3. הוסף ל-GitHub Secrets בשם GPLAY_AUTH_TOKEN

# 4. הרץ את ה-workflow - הוא ישתמש בטוקן שלך אוטומטית
```

זהו! אין צורך להתמודד עם חסימות dispenser ב-GitHub Actions.
