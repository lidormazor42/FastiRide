# ספר הפרויקט — FastiRide

פרויקט גמר DevOps: אפליקציה עובדת, בקונטיינרים, פרוסה לקלאסטר Kubernetes מנוהל (AWS EKS), עם CI/CD ו-GitOps מלאים, וניטור אמיתי — הכל מוגדר כקוד.

---

## 1. מבוא לפרויקט

FastiRide היא פלטפורמת שיתוף נסיעות לפסטיבלים — נהגים מפרסמים נסיעה, משתתפים אחרים מצטרפים אליה, וצ'אט פרטי נפתח בין הנהג לנוסעים המאושרים. האפליקציה עצמה היא כלי להדגמת פרויקט DevOps מלא — הדגש הוא על **איך** היא בנויה, נבדקת, נפרסת ומנוטרת, לא רק על מה שהיא עושה.

## 2. מטרת המערכת

להקים ולתפעל אפליקציה אמיתית בסביבת DevOps מלאה: מקוד מקומי, דרך Docker ו-Kubernetes, עם pipeline אוטומטי לחלוטין (push → build → deploy), ותשתית שכולה מוגדרת כקוד (Terraform) — כולל את שכבת הניטור עצמה, לא רק את האפליקציה.

## 3. הסבר על האפליקציה

- **Frontend:** HTML/JS פשוט מוגש דרך Nginx — בלי build step, כדי לשמור את ה-container קטן.
- **Backend:** FastAPI (Python), עם endpoints ל-אירועים, נסיעות, הצטרפות/אישור, צ'אט (WebSocket), ואימות כרטיסים (AWS Rekognition).
- **Database:** Amazon RDS ל-PostgreSQL (במקור היה StatefulSet בתוך הקלאסטר — עבר מיגרציה אמיתית, ראו סעיף 13).
- **אימות:** Google OAuth, session מבוסס JWT ב-cookie (המפתח החותם נשמר ב-SSM Parameter Store, לא בקוד).
- **התראות:** Amazon SES למיילים לנהגים כשמישהו מצטרף/מבטל — תבניות HTML ממותגות בעיצוב האתר.
- **אימות כרטיסים — החלטת תכנון:** ה-OCR הראשי הוא AWS Rekognition (מנוהל, בלי תלויות native), אבל pytesseract נשאר בכוונה כ-fallback מקומי — כך האפליקציה עובדת גם ב-docker compose מקומי בלי חיבור ל-AWS. זו לא שארית ישנה אלא degradation מדורג מכוון: ענן קודם, מקומי כגיבוי.

## 4. ארכיטקטורת המערכת

דיאגרמה מלאה + טבלת סביבות + לוג החלטות FinOps נמצאים ב-[README.md](README.md#architecture) (Mermaid diagram שמוצג ישירות ב-GitHub). בקצרה: VPC עם 2 Availability Zones, subnets ציבוריים (ALB + NAT Instance) ו-subnets פרטיים (EKS nodes + RDS), ALB אחד משותף בין האפליקציה ל-Grafana, ו-Route 53 ל-`fastiride.app`.

## 5. הסבר על כל כלי

| כלי | תפקיד בפועל בפרויקט |
|---|---|
| **Docker** | אורז את ה-backend וה-frontend ל-images עצמאיים, אותו image רץ מקומית (docker compose) ובענן (EKS) |
| **Kubernetes (EKS)** | מריץ את ה-pods, שומר עליהם חיים (self-healing), מנתב תעבורה (Service/Ingress), ומאפשר לגדול (replicas) |
| **Helm** | "תבנית" אחת לכל המניפסטים של Kubernetes, עם קובץ values שונה לכל סביבה (dev מקומי מול prod ב-AWS) |
| **Terraform** | מגדיר כל משאב ב-AWS כקוד — VPC, EKS, RDS, S3, IAM, Route53 — כדי שהתשתית תהיה נבנית-מחדש ובת-שחזור, לא "נלחצה" ב-console |
| **GitHub Actions** | ה-CI: על כל push — lint, הרצת בדיקות (pytest), בניית images, דחיפה ל-ECR |
| **ArgoCD** | ה-CD: קורא את המצב הרצוי מ-Git ומיישם אותו על הקלאסטר לבד — לא ה-CI "דוחף" לקלאסטר, אלא ArgoCD "מושך" מ-Git |
| **Prometheus** | אוסף מדדים (metrics) — גם על הקלאסטר עצמו וגם על ה-backend (endpoint ייעודי `/metrics`) |
| **Grafana** | מציג את המדדים כדשבורדים — כולל דשבורד מותאם אישית שבניתי לפי שיטת RED (Rate/Errors/Duration) |
| **Loki** | אוסף לוגים מכל ה-pods (חלופה קלה יותר ל-Elasticsearch) |
| **Alertmanager** | שולח **מייל אמיתי** כשמשהו לא תקין — לא רק "יש דשבורד שאיש לא מסתכל עליו" |

## 6. תהליך העבודה

עבודה לפי **GitHub Flow** (לא GitFlow — אין ענף `develop` ארוך-טווח): `feature/*` קצר לכל שינוי, Pull Request ישירות ל-`main` (branch protection — PR חובה, lint+tests רצים). כל merge ל-`main` **מפרס אוטומטית ל-staging** (`staging.fastiride.app`). כשמוכן להעלות לפרודקשן בפועל, דוחפים git tag (`git tag v1.2.0 && git push origin v1.2.0`) — זה מריץ workflow נפרד שמעלה בדיוק את אותו image שכבר נבדק ב-staging ל-production (`fastiride.app`), **בלי build מחדש**. ראו סעיף 4 להרחבה.

## 7. Pipeline (CI/CD)

שני קבצי workflow, אחראים על שני deploy triggers שונים:

**`.github/workflows/ci.yaml`** — רץ על כל push/PR ל-`main`, שלושה jobs:
1. **Lint** — `ruff` על קוד ה-Python.
2. **Test** — `pytest` על סוויטת בדיקות אמיתית (backend/tests/) — מריץ מול sqlite בזיכרון, לא תלוי בשום שירות חיצוני.
3. **Deploy to Staging** (רק על push ל-`main`, ורק אם שני הקודמים עברו) — בונה image ל-backend ול-frontend, דוחף ל-ECR, ואז **מעדכן את tag ה-image ב-`values-staging.yaml` ב-Git עצמו** (לא נוגע בקלאסטר!) — זה ה"טריגר" ש-ArgoCD מזהה ומסנכרן ל-staging.

**`.github/workflows/promote-to-production.yaml`** — רץ **רק** כשדוחפים git tag בפורמט `v*`. לא בונה שום image חדש — קורא את ה-tags הנוכחיים מ-`values-staging.yaml` (מה שכבר רץ ואומת ב-staging) וכותב אותם ל-`values-prod.yaml`. כך production תמיד מריץ בדיוק את מה ש"עבר" ב-staging, לא build עצמאי.

**`.github/workflows/iac-quality.yaml`** — ה-CI של התשתית עצמה, לא רק של הקוד: `terraform fmt -check` + `terraform validate` (רץ בלי credentials בכלל, עם `-backend=false`), `helm lint` מול קבצי ה-values של **שתי** הסביבות, וסריקת אבטחה של **Trivy** — פגיעויות CRITICAL בתלויות Python או misconfigurations ב-Terraform/K8s מפילות את ה-pipeline; ממצאי HIGH מדווחים בלוג לבחינה.

## 8. Kubernetes

משאבים בשימוש: `Deployment` (backend, frontend — עם resources requests/limits אמיתיים), `Service`, `Ingress` (עם AWS Load Balancer Controller, ALB אחד משותף לאפליקציה ול-Grafana), `HPA` (מוגדר, כבוי כברירת מחדל בפרויקט קטן זה), ו-`CronJob` (גיבוי יומי של ה-DB ל-S3). **Pod** הוא יחידת הריצה הבסיסית (container אחד או יותר, רשת/אחסון משותפים); **Deployment** שומר על מספר replicas רצוי ומחליף pods שנופלים; **Service** נותן DNS/IP יציב לקבוצת pods גם כשהם מוחלפים.

## 9. Docker

Dockerfile ייעודי ל-backend ול-frontend. ה-backend דורש ספריות מערכת (`libzbar0`, `tesseract-ocr`) לפני `pip install` — לכן ה-image נבנה בשכבות (system deps → python deps → קוד), כדי ש-Docker ישתמש ב-cache וידלג על שלבים שלא השתנו. ה-image הזהה בדיוק רץ גם מקומית (docker compose) וגם בענן — זה כל הפואנטה של containers: "עובד אצלי" הופך ל"עובד בכל מקום".

**Hardening:** ה-backend רץ כמשתמש לא-root (`USER appuser` ב-Dockerfile) — אם האפליקציה נפרצת (למשל דרך קובץ תמונה זדוני בהעלאת כרטיס), התוקף לא מקבל root בתוך ה-container. פורט 8000 לא-מיוחס, אז לא נדרש שום שינוי נוסף.

## 10. Terraform

כל התשתית תחת `terraform/`, עם state מרוחק ב-S3 (לא local state file) **ונעילת state** (`use_lockfile = true` — נעילה native ב-S3 מ-Terraform 1.10, בלי צורך בטבלת DynamoDB) שמונעת משני `apply` מקבילים להשחית את ה-state. מודולים: `vpc`, `eks`, `rds`, `uploads` (S3), `dns` (Route53), `github-oidc`. כל מודול אחראי על משאב AWS אחד — לא קובץ ענק אחד עם הכל מעורבב.

**ניהול סודות — הכל דרך SSM Parameter Store (SecureString):** סיסמת ה-RDS, המפתח שחותם sessions של משתמשים, וסיסמת ה-admin של Grafana — כולם נוצרים ב-`random_password` של Terraform ונשמרים ב-SSM. אף סוד לא מופיע בקוד או ב-Git; סקריפט ה-bootstrap קורא אותם מ-SSM בזמן הקמה ובונה מהם Kubernetes Secrets. (במקור סיסמת Grafana וה-session secret היו hardcoded בסקריפט — זוהה ותוקן ב-audit אבטחה לפני ההגשה.)

## 11. Monitoring

Prometheus + Grafana + Loki + Alertmanager — **כולם עצמם פרוסים דרך ArgoCD**, לא helm ידני, כדי לשמור על עקביות GitOps גם עבור התשתית שמנטרת את האפליקציה. דשבורד מותאם אישית (`fastiride-backend`) בנוי על מדדים אמיתיים מה-backend (לא רק דשבורד קהילתי גנרי). Alertmanager מחובר בפועל ל-SES ושולח מייל אמיתי — לא רק "יש alert rules שאף אחד לא רואה".

## 12. Screenshots

ראו `docs/images/` (רשימת הצילומים הנדרשים מפורטת ב-[README](README.md#screenshots)) — לוח הנסיעות, ArgoCD עם כל האפליקציות Synced/Healthy, שני דשבורדי Grafana, ריצת CI ירוקה, ומסך ה-RDS.

## 13. בעיות ופתרונות

זה החלק המעניין באמת — לא "הכל עבד מהפעם הראשונה", אלא סדרת תקלות אמיתיות שנתקלתי בהן ופתרתי:

**תקלת עלות — קלאסטר נטוש בפרנקפורט ($153).** בדיקת חיוב AWS שגרתית חשפה קלאסטר EKS מלא שרץ ב-`eu-central-1` במשך כחודש, לא מנוהל ב-Terraform בכלל. אומת דרך Route53 שהוא לא משרת תעבורה אמיתית, ונמחק. **לקח:** בדיקת עלויות חייבת לסרוק כמה regions, לא רק את זה שבשימוש.

**באג IRSA — הרשאות AWS מעולם לא עבדו בפועל.** ה-trust policy של ה-IAM role לבקנד הצביע על namespace שגוי (`fastiride` במקום `fastiride-prod`) — כל קריאה ל-Rekognition/S3 נכשלה בשקט ונפלה חזרה ל-OCR מקומי, בלי הודעת שגיאה גלויה. התגלה רק כשבדקתי לוגים תוך כדי בדיקה חיה על AWS — לא מספיק לבדוק ב-Docker מקומי בלבד.

**ArgoCD selfHeal מוחק שינויים ידניים.** תיקון שהוחל ישירות דרך `helm upgrade` (בלי git push) נמחק תוך דקה על ידי ה-sync האוטומטי של ArgoCD, כי הוא קורא את המצב הרצוי **מ-Git בלבד**. הלקח חזר על עצמו כמה פעמים באותה צורה — Git הוא מקור האמת היחיד, אין "לתקן מהר בצד".

**404 שקטים על ה-health check של ה-ALB.** ה-Load Balancer בדק ברירת מחדל את הנתיב `/` על ה-backend — אבל ה-API לא מגדיר route כזה בכלל. כל בדיקה נכשלה ב-404 כל 10-30 שניות, מה שזיהם את מדדי השגיאות (44% error rate מדומה!) בלי שום השפעה אמיתית על המשתמשים. תוקן עם annotation ממוקד רק ל-Service של ה-backend.

**באג מיזוג Helm ב-Alertmanager.** Helm ממזג dictionaries אך **מחליף arrays לגמרי**. הגדרת `receivers` מותאמת אישית מחקה בטעות receiver בשם `"null"` שחוק ברירת המחדל (השתקת התראת Watchdog) עדיין הצביע עליו — Alertmanager פשוט לא עלה, עד שהוחזר receiver תואם.

**PVC יתומים — שלוש פעמים.** `helm uninstall` לא מוחק PVC-ים שנוצרו דרך StatefulSet — קרה עם Postgres, ואז שוב עם Prometheus/Loki אחרי מעבר ל-ArgoCD. לקח: כל migration/uninstall של StatefulSet חייב בדיקת `kubectl get pvc` נפרדת, לא לסמוך על ניקוי אוטומטי.

**Deadlock בפריסה של Grafana.** Volume מסוג `ReadWriteOnce` + אסטרטגיית ברירת המחדל `RollingUpdate` (עם replica יחיד) יוצרים מבוי סתום — ה-pod החדש לא יכול לתפוס את ה-volume כל עוד הישן מחזיק בו, אבל הישן לא מתבטל עד שהחדש מוכן. פתרון: `strategy.type: Recreate`.

**Node לא הצליח להצטרף לקלאסטר.** בניסיון להעלות את מגבלת ה-pods per-node (מ-17 ל-110, דרך prefix delegation), Terraform apply נכשל: `User data was not in the MIME multipart format`. EKS דורש עטיפת MIME multipart ספציפית סביב הגדרת ה-NodeConfig, לא YAML גולמי — גם אם הוא תקין. תוקן, ואומת: שני ה-nodes עלו עם קיבולת 110 pods במקום 17.

**מיגרציה ל-RDS.** במקור Postgres רץ כ-StatefulSet בתוך הקלאסטר (כדי לחסוך עלות בשלב הפיתוח המהיר). לקראת ההגשה, בוצעה מיגרציה מלאה ל-RDS מנוהל: מודול Terraform חדש, סיסמה שנוצרת אקראית ונשמרת ב-SSM Parameter Store (לא בקוד), עדכון סקריפטי ה-bootstrap/teardown, והסרת ה-StatefulSet מה-Helm chart. אומת מקצה לקצה: 7 הטבלאות נוצרו נכון על ה-RDS דרך ה-migration הפנימי של האפליקציה.

**מיילים לנהגים נכשלו בשקט — מהיום הראשון.** פיצ'ר ההתראות במייל (בקשת הצטרפות לנסיעה) "עבד" לכאורה מאז שנבנה — אבל בפועל אף מייל לא נשלח מעולם: כתובת השולח `noreply@fastiride.app` מעולם לא אומתה ב-SES, וה-`try/except` בקוד בלע את השגיאה ונפל לחלופת console-print. התגלה רק כשמשתמש אמיתי (אני) שם לב שמייל לא הגיע. אבחון: הרצת פונקציית השליחה ישירות בתוך ה-pod (`kubectl exec`) חשפה `Email address is not verified`. פתרון: אימות **הדומיין כולו** ב-SES דרך DKIM — שלוש רשומות CNAME ב-Route53, הכל ב-Terraform (`ses-domain.tf`), בלי שום קליק ידני. **שני לקחים:** (1) fallback שקט מדי מסתיר תקלות — הוא נועד לפיתוח מקומי אבל הסווה כשל אמיתי בפרודקשן; (2) בדיקה פונקציונלית אמיתית (המייל הגיע?) שווה יותר מקוד שנראה תקין.

**קונפליקט בעלות בין Helm ל-ArgoCD.** סקריפט ה-bootstrap הריץ `helm upgrade --install` על release שבפועל היה מנוהל כולו על ידי ArgoCD — והתקבלה שגיאת `invalid ownership metadata: missing key "meta.helm.sh/release-name"`. הסיבה: משאב שנוצר על ידי ArgoCD מקבל רק את annotation המעקב של ArgoCD, לא את annotations הבעלות של Helm — ולכן Helm מסרב "לאמץ" אותו. תיקון נקודתי: הוספת ה-annotations ידנית. תיקון מבני: הסרת פקודות ה-helm הידניות מהסקריפט לגמרי — ArgoCD הוא הכותב **היחיד** של המניפסטים האלה, מהפריסה הראשונה ועד הסוף. שני כלים שמנהלים אותו משאב זה תמיד באג שמחכה לקרות.

**CI לא הצליח לדחוף ל-branch מוגן.** אחרי הפעלת branch protection על `main` (חובת PR), ה-job שמעדכן את tag ה-image ב-Git נכשל עם `GH006: Protected branch update failed` — ה-`GITHUB_TOKEN` המובנה של Actions כפוף לחוקי ההגנה, וב-repo אישי (לא ארגוני) GitHub לא תומך בהגדרת bypass ל-apps. הפתרון: שימוש ב-Personal Access Token של בעל ה-repo (secret בשם `GH_PAT`) בשלב ה-checkout — הטוקן של הבעלים עצמו פטור מחובת ה-PR (כש-`enforce_admins` כבוי). שלושה ניסיונות `gh api` נכשלו עד שהתבררה הסמנטיקה המדויקת של ה-API הזה על repos אישיים.

**ArgoCD לא הצליח לסנכרן את ה-CRDs של Prometheus.** בהקמת קלאסטר מלאה, `monitoring-prometheus` נתקע ב-`OutOfSync` עם שגיאה `metadata.annotations: Too long: may not be more than 262144 bytes`. הסיבה: ה-CRDs של kube-prometheus-stack גדולים מספיק שה-annotation של client-side apply (`last-applied-configuration`, ששומר את כל הקונפיגורציה הקודמת לצורך 3-way diff) חורג מהמגבלה של Kubernetes על annotations. הפתרון המתועד: `syncOptions: [ServerSideApply=true]`, ששומר בעלות per-field במקום annotation שלם. בעיה שנייה, נסתרת יותר, צצה מיד אחרי: ה-Prometheus Operator עצמו **עלה לפני** שה-CRDs נוצרו בהצלחה, רשם בלוג "resource not installed" בזמן ה-startup, ולא בדק שוב מעולם — נדרש `kubectl rollout restart` ידני כדי שיגלה מחדש את ה-CRDs שכבר קיימים. לקח: race condition בזמן bootstrap יכול "להיתקע" ברכיב שכבר עלה, לא רק במשאב שעדיין לא נוצר — restart הוא כלי אבחון לגיטימי, לא רק "פתרון קסם".

**אימות כרטיסים היה ניתן לעקיפה מלאה — תוקן אחרי דיון על מודל האיום.** הבדיקה המקורית (`_ticket_matches`) בדקה רק אם מילות שם האירוע מופיעות בטקסט שזוהה בתמונה (OCR/ברקוד) — עקיפה טריוויאלית: כל תמונה עם הטקסט הנכון "כתוב עליה" בעורך תמונות עברה. התיקון עבר כמה סבבי חשיבה אמיתיים: קודם נבדקה אפשרות לחבר API למערכת הכרטיסים של המפיק — נפסלה, כי (א) לא ריאלית טכנית מול פלטפורמות כרטוס שונות ללא הסכם עסקי, ו-(ב) **גם אם הייתה ריאלית, לא הייתה סוגרת את הסיכון האמיתי** — כרטיס הוא מוצר שכל אחד יכול לרכוש, כולל גורם עוין; אימות "זה כרטיס אמיתי" לא שקול לבדיקת זהות. ההבנה המשמעותית: בתרבות הפסטיבלים בישראל מפיקים מבצעים בפועל סלקציה על מי מקבל כרטיס — כך שאימות "האם זה כרטיס אמיתי שהמפיק הנפיק" יורש בעקיפין את תהליך הסלקציה שהמפיק כבר ביצע. הפתרון הסופי, שכבות: (1) ברקוד/QR קריא הפך לחובה — סוגר "אין בכלל כרטיס אמיתי"; (2) המפיק יכול להעלות (אופציונלי, בזמן יצירת האירוע, ניתן להוסיף עוד בכל שלב) דוגמאות של כרטיסים אמיתיים; (3) כשקיימות דוגמאות, **דמיון חזותי (average-hash, ללא תלות חדשה) הוא הסימן היחיד שמחליט — טקסט לא משתתף בהחלטה בכלל**, כי טקסט הוא בדיוק מה שתוקף שולט בו; ניסיון ראשוני שכלל fallback לטקסט כשהדמיון החזותי נכשל התגלה כפרצה מחדש (בדיוק שם תוקף עם כרטיס ישן+טקסט מזויף היה עובר) ותוקן. אומת עם תמונות סינתטיות: כרטיס ישן עם שם מודבק (עיצוב שונה, ברקוד אמיתי) — נחסם; קונה מסבב מכירה שני (אותה תבנית, תווית שונה) — עדיין עובר, כי hash תפיסתי סלחני לשינויים מקומיים קטנים ונוקשה רק כלפי עיצוב שונה לגמרי.

## 14. תמונות קוד

מומלץ לצלם ולהוסיף כאן קטעי קוד מייצגים מהריפו:
- `backend/main.py` — חיבור ה-`/metrics` endpoint (`Instrumentator().instrument(app).expose(app)`)
- `helm/fastiride/templates/postgres-backup-cronjob.yaml` — ה-CronJob המלא
- `terraform/modules/rds/main.tf` — הגדרת ה-RDS
- `terraform/ses-alerting.tf` — זהות ה-SES וה-IAM user ל-Alertmanager
- `.github/workflows/ci.yaml` — ה-pipeline המלא (lint → test → build → GitOps bump)
- `backend/tests/test_join_flow.py` — דוגמה לבדיקת unit test אמיתית

## 15. סיכום אישי

_(לכתוב אישית — מה למדת, מה היה הכי מאתגר, מה היית עושה אחרת בפעם הבאה)_

---

## נספח: הכנה לשאלות הבוחן

תשובות מקושרות ישירות לפרויקט הזה, לא הגדרות כלליות מהאינטרנט:

**מה Docker עושה?**
אורז את האפליקציה (קוד + תלויות + ספריות מערכת כמו `libzbar0`) ל-image אחד עצמאי, שרץ זהה בכל מקום — אצלי מקומית ובענן זה בדיוק אותו `fastiride-backend` image.

**למה Kubernetes?**
כי EC2 בודד לא מחזיר את עצמו לחיים כשהוא קורס. Kubernetes שומר על מספר replicas רצוי (backend, frontend), מנתב תעבורה גם כש-pods מוחלפים (Service), ומאפשר deploy בלי downtime (rolling update).

**מה קורה כשעושים Push?**
ל-`main` (אחרי merge של PR): GitHub Actions מריץ lint ואז pytest. אם שניהם עוברים — בונה images, דוחף ל-ECR, ומעדכן את ה-tag ב-`values-staging.yaml` **ב-Git עצמו** (לא נוגע בקלאסטר ישירות). זה מפרס ל-**staging בלבד**, אוטומטית, בכל merge.

**איך מתבצע Deployment?**
ArgoCD סורק את ה-repo כל ~2 דקות, ורואה שקובץ ה-values השתנה — מיישם את זה לקלאסטר לבד. אני אף פעם לא מריץ `kubectl apply` או `helm upgrade` ידנית. **production לא מתעדכן ממש merge** — רק כשדוחפים git tag בפורמט `vX.Y.Z`, מה שמריץ workflow נפרד (`promote-to-production.yaml`) שמעתיק את ה-tags הקיימים מ-`values-staging.yaml` (image שכבר נבנה ונבדק) לתוך `values-prod.yaml` — בלי build מחדש. כך production תמיד מריץ בדיוק את מה שכבר עבד ב-staging.

**למה Terraform?**
כי אחרת התשתית קיימת רק "בראש שלי" ובקונסולת AWS — בלתי אפשרי לשחזר, לבדוק, או להסביר במדויק מה קיים ולמה. עם Terraform, `terraform destroy` ואז `terraform apply` בונים בדיוק אותה תשתית מחדש.

**איך Grafana מתחברת?**
דרך שני datasources מוגדרים מראש (Prometheus ל-metrics, Loki ל-logs) — כתובות ה-Service הפנימיות שלהם בקלאסטר (`monitoring-prometheus-kube-prometheus.monitoring.svc.cluster.local:9090` וכו').

**מה ArgoCD עושה?**
"מושך" את המצב הרצוי מ-Git ומיישם אותו — בניגוד ל-CI ש"דוחף". ArgoCD גם מזהה סטייה (drift) בין מה שרץ בפועל למה שכתוב ב-Git ומתקן אותה אוטומטית (`selfHeal`) — נתקלתי בזה בפועל כשתיקון ידני שלא הגיע ל-Git נמחק תוך דקה.

**איך המערכת מתעדכנת לבד?**
לולאת ה-GitOps: push → CI בונה ומעדכן tag ב-Git → ArgoCD מזהה ומסנכרן. אף אדם לא נוגע בקלאסטר בין השלבים האלה.

**איפה הסודות של המערכת?**
ב-AWS SSM Parameter Store, כ-SecureString: סיסמת RDS, מפתח חתימת ה-sessions, סיסמת Grafana. נוצרים על ידי Terraform (`random_password`), נקראים על ידי סקריפט ה-bootstrap שבונה מהם Kubernetes Secrets. שום סוד לא נמצא ב-Git — ה-`.env` המקומי ב-`.gitignore`, וההרשאות בקלאסטר מבוססות IRSA (תפקיד IAM לכל ServiceAccount) בלי מפתחות סטטיים.

**מה קורה אם ה-DB נמחק?**
CronJob יומי מריץ `pg_dump`, דוחס ומעלה ל-S3 (`db-backups/`), עם ההרשאות של אותו IRSA role שכבר יש ל-backend (בלי IAM חדש). בנוסף, RDS מנוהל עם גיבויים אוטומטיים של AWS. השחזור: `pg_restore` מהקובץ האחרון ב-S3.

**איך אתה יודע שהמערכת בריאה עכשיו?**
שלוש שכבות: probes של Kubernetes (liveness/readiness על כל pod), דשבורד RED ב-Grafana (Rate/Errors/Duration על ה-API האמיתי), ו-Alertmanager ששולח מייל אמיתי דרך SES אם alert נדלק — כולל alert על backend שלא מגיב.

**האם אימות הכרטיסים באפליקציה באמת מונע הונאה?**
לא, ולא מתיימר. גם עם הבדיקה המשודרגת (ברקוד חובה + דמיון חזותי לכרטיס אמיתי) — מי שבאמת רוצה להיכנס יכול פשוט לרכוש כרטיס לגיטימי, כי כרטיס הוא מוצר שכל אחד יכול לקנות; זו לא בדיקת זהות. המטרה של הבדיקה היא לסנן כניסה **אקראית ומזדמנת** לקבוצת הטרמפים (מישהו שמעתיק טקסט בעורך תמונות), לא להחליף אבטחה פיזית באירוע עצמו. חשוב לי שזה יהיה כתוב וברור, לא רק "עובד" — פתרון שמציג ביטחון-שווא גרוע יותר מהודאה בגבולות שלו.
