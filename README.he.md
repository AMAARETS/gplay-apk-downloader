# GPlay APK Downloader

הורדת APK מ-Google Play Store. מיזוג אוטומטי של split APKs (App Bundles) לקובץ APK יחיד להתקנה.

## תכונות

- הורדת כל אפליקציה חינמית מ-Google Play
- מיזוג אוטומטי של split APKs באמצעות [APKEditor](https://github.com/REAndroid/APKEditor)
- תמיכה בארכיטקטורות: ARM64 (טלפונים מודרניים) ו-ARMv7 (טלפונים ישנים)
- ממשק אינטרנט עם התקדמות בזמן אמת
- כלי CLI לסקריפטים ואוטומציה
- אפליקציות ללא splits שומרות על החתימה המקורית
- APKs ממוזגים נחתמים עם debug keystore

---

## GitHub Actions - הורדה אוטומטית

### שימוש ב-GitHub Actions

הפרויקט כולל GitHub Action שמאפשר להוריד APK ישירות דרך GitHub ולשמור אותם כגרסאות.

#### הוראות שימוש:

1. עבור ל-**Actions** בגיטהאב
2. בחר **"Download APK from Google Play"**
3. לחץ **"Run workflow"**
4. מלא את הפרמטרים:
   - **Package name**: שם החבילה (למשל `com.whatsapp`)
   - **Architecture**: 
     - `arm64` - טלפונים מודרניים (2016+)
     - `armv7` - טלפונים ישנים
   - **Merge splits**: סמן כדי למזג split APKs לקובץ אחד
   - **Release tag**: תג אופציונלי (אם ריק, יוצר אוטומטית)

5. ה-APK יופיע ב-**Releases** של המאגר

#### תכונות:
- ✅ ניסיונות חוזרים אוטומטיים עד קבלת טוקן תקין
- ✅ מטמון לתלויות (Python, Java, APKEditor) להאצת הרצות
- ✅ יצירת Release אוטומטית עם מידע על האפליקציה
- ✅ תג גרסה אוטומטי: `{app}-{arch}-v{version}-{timestamp}`
- ✅ ולידציה של טוקן לפני שימוש

#### דוגמאות:

**הורדת WhatsApp (ARM64, ממוזג):**
- Package: `com.whatsapp`
- Architecture: `arm64`
- Merge splits: ✓

**הורדת Instagram לטלפון ישן (ARMv7):**
- Package: `com.instagram.android`
- Architecture: `armv7`
- Merge splits: ✓

---

## התקנה מקומית

### דרישות מקדימות

- Python 3.8+
- Java 17+ (עבור APKEditor)
- apksigner (לחתימת APK)

### התקנה מהירה

```bash
git clone <repo-url> gplay-downloader
cd gplay-downloader
./setup.sh
```

### תלויות ידניות (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre-headless apksigner python3 python3-venv python3-pip curl
```

---

## ממשק אינטרנט

### הפעלת השרת

```bash
./start-server.sh
```

השרת רץ ברקע על פורט 5000. פתח http://localhost:5000 בדפדפן.

### שימוש בממשק

1. **הזן שם חבילה** (למשל `com.google.android.youtube`)
2. **בחר ארכיטקטורה**:
   - ARM64 - טלפונים מודרניים (2016+)
   - ARMv7 - טלפונים ישנים
3. **בחר אופציית מיזוג**:
   - מסומן: APK יחיד להתקנה (חתום מחדש)
   - לא מסומן: ZIP עם base + split APKs
4. **לחץ Download**

### הערה חשובה

> **אזהרת חתימה**: APKs ממוזגים נחתמים מחדש עם מפתח debug ולא יקבלו עדכונים אוטומטיים מ-Google Play. אפליקציות ללא splits שומרות על החתימה המקורית.

---

## ממשק שורת פקודה (CLI)

### הגדרה ראשונית

אימות לקבלת טוקן אנונימי:

```bash
./gplay auth
```

הטוקן נשמר ב-`~/.gplay-auth.json` ומשותף בין CLI לשרת.

### פקודות

#### חיפוש אפליקציות

```bash
./gplay search "youtube"
./gplay search "file manager" -l 20    # הצג 20 תוצאות
```

#### מידע על אפליקציה

```bash
./gplay info com.google.android.youtube
```

#### הורדת APK

```bash
# הורדה בסיסית (ARM64 ברירת מחדל)
./gplay download com.google.android.youtube

# ARM64 מפורש (טלפונים מודרניים)
./gplay download com.google.android.youtube -a arm64

# ARMv7 (טלפונים ישנים)
./gplay download com.google.android.youtube -a armv7

# הורדה ומיזוג splits לקובץ אחד
./gplay download com.google.android.youtube -m

# ARM64 ממוזג
./gplay download com.google.android.youtube -m -a arm64

# ARMv7 ממוזג
./gplay download com.google.android.youtube -m -a armv7

# דוגמה מלאה: מיזוג, armv7, תיקיית פלט מותאמת
./gplay download com.google.android.youtube -m -a armv7 -o ~/apks/
```

### אופציות CLI

| אופציה | תיאור |
|--------|-------|
| `-a`, `--arch` | ארכיטקטורה: `arm64` (ברירת מחדל) או `armv7` |
| `-m`, `--merge` | מיזוג split APKs לקובץ יחיד להתקנה |
| `-o`, `--output` | תיקיית פלט (ברירת מחדל: תיקייה נוכחית) |
| `-v`, `--version` | הורדת גרסה ספציפית (version code) |

### דוגמאות

```bash
# הורדת YouTube, מיזוג splits, ARM64 (ברירת מחדל)
./gplay download com.google.android.youtube -m

# הורדת Instagram לטלפון ישן (ARMv7)
./gplay download com.instagram.android -m -a armv7

# הורדה לתיקייה ספציפית
./gplay download com.whatsapp -m -o ~/Downloads/

# הורדה ללא מיזוג (שומר splits נפרדים)
./gplay download com.google.android.youtube -a arm64

# חיפוש והורדה
./gplay search "spotify"
./gplay download com.spotify.music -m -a arm64
```

---

## פתרון בעיות

### "Auth file not found"
הרץ `./gplay auth` קודם כדי לקבל טוקן אימות.

### "APKEditor.jar not found"
הרץ מחדש `./setup.sh` להורדת APKEditor.

### השרת לא מתחיל
בדוק אם פורט 5000 תפוס:
```bash
lsof -i:5000
kill $(lsof -ti:5000)  # הרוג תהליך קיים
```

### שגיאות DNS ב-VPS
חלק מספקי VPS חוסמים את Google CDN. נסה:
```bash
# השתמש ב-Google DNS
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

### ההורדה נכשלת שוב ושוב
טוקנים מה-dispenser משתנים באיכותם. הכלי מנסה אוטומטית עם טוקנים חדשים עד להצלחה.

---

## רישיון

MIT
