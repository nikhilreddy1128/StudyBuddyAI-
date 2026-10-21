import json
import html
import os
from datetime import date, timedelta, datetime, time
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
import streamlit as st

import streamlit.components.v1 as components

# Optional hosted account + shared lobby services. Configure as Streamlit secrets or env vars.
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL", "")).rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_ANON_KEY", "")
SUPABASE_READY = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
LOCAL_STORE = components.declare_component("studybuddy_local_store", path=str(Path(__file__).parent / "components" / "local_store"))
_AUTH_KEY = "studybuddy_auth"

def _sb_headers(token=None, prefer=None):
    h = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token or SUPABASE_ANON_KEY}",
         "Content-Type": "application/json"}
    if prefer: h["Prefer"] = prefer
    return h

def _auth_request(path, payload):
    r = requests.post(f"{SUPABASE_URL}/auth/v1/{path}", json=payload, headers=_sb_headers(), timeout=20)
    if r.status_code >= 400:
        try: msg = r.json().get("msg") or r.json().get("message") or r.json().get("error_description")
        except Exception: msg = r.text[:250]
        raise ValueError(msg or "Authentication failed.")
    return r.json()

def show_auth_gate():
    # Passwords are sent only to Supabase Auth; never saved in app files.
    if not SUPABASE_READY or st.session_state.get(_AUTH_KEY, {}).get("access_token"):
        return True
    st.markdown("# ✦ StudyBuddyAI")
    st.caption("Sign in to keep your learning progress separate from other learners.")
    mode = st.radio("Account", ["Log in", "Create account"], horizontal=True)
    with st.form("studybuddy_auth_form"):
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", help="Use at least 8 characters.")
        submitted = st.form_submit_button("Continue ✦", use_container_width=True)
    if submitted:
        try:
            if not email.strip() or len(password) < 8:
                raise ValueError("Enter your email and a password with at least 8 characters.")
            if mode == "Create account":
                result = _auth_request("signup", {"email": email.strip(), "password": password})
                if not result.get("access_token"):
                    st.success("Account created. Check your email if confirmation is enabled, then log in.")
                    return False
            else:
                result = _auth_request("token?grant_type=password", {"email": email.strip(), "password": password})
            st.session_state[_AUTH_KEY] = result
            st.rerun()
        except Exception as exc:
            st.error(f"Could not continue: {exc}")
    st.info("Without Supabase credentials the app runs in local/demo mode. Setup instructions are included in the project.")
    return False

st.set_page_config(page_title="StudyBuddy AI", page_icon="😄", layout="wide", initial_sidebar_state="expanded")

if not show_auth_gate():
    st.stop()

DATA = Path(os.environ.get("STUDYBUDDY_DATA_FILE", str(Path(__file__).with_name("study_data.json"))))
if not DATA.exists() and Path(__file__).with_name("studydaya.json").exists():
    DATA = Path(__file__).with_name("studydaya.json")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
DEFAULT_TOPICS = {
    "Mathematics": ["Sets", "Relations and Functions", "Trigonometric Functions", "Mathematical Induction", "Complex Numbers"],
    "Physics": ["Physical World", "Units and Measurements", "Motion in a Straight Line", "Motion in a Plane", "Laws of Motion"],
    "Chemistry": ["Some Basic Concepts", "Structure of Atom", "Classification of Elements", "Chemical Bonding", "States of Matter"],
}
QUIZ = [
    ("Which is a well-defined collection?", ["Beautiful flowers", "Tall students", "Prime numbers less than 10", "Interesting books"], 2, "A set must be well-defined; primality and being less than 10 are objectively testable."),
    ("If A = {1, 2, 3}, how many elements are in A?", ["1", "2", "3", "6"], 2, "There are three distinct elements."),
    ("Which symbol means 'is an element of'?", ["⊂", "∈", "∪", "∩"], 1, "∈ means an object belongs to a set."),
    ("If A = {1, 2} and B = {2, 3}, what is A ∪ B?", ["{2}", "{1, 3}", "{1, 2, 3}", "{1, 2, 2, 3}"], 2, "The union contains all distinct elements from either set."),
    ("If A = {1, 2, 3} and B = {2, 3, 4}, what is A ∩ B?", ["{1, 4}", "{1, 2, 3, 4}", "{2, 3}", "∅"], 2, "The intersection contains elements shared by both sets."),
    ("A set containing no elements is called:", ["Universal set", "Singleton set", "Empty set", "Infinite set"], 2, "The empty set is denoted by ∅ or {}."),
    ("If A = {a, b}, how many subsets does A have?", ["2", "3", "4", "5"], 2, "A set with n elements has 2ⁿ subsets, so 2² = 4."),
    ("If A ⊆ B, which statement must be true?", ["Every element of A is in B", "Every element of B is in A", "They are disjoint", "A is empty"], 0, "A is a subset of B when every element of A is also in B."),
    ("If U = {1, 2, 3, 4} and A = {1, 3}, what is A′?", ["{1, 3}", "{2, 4}", "{1, 2, 3, 4}", "∅"], 1, "The complement contains the elements in U that are not in A."),
    ("If n(A)=5, n(B)=4 and n(A ∩ B)=2, find n(A ∪ B).", ["11", "9", "7", "2"], 2, "n(A ∪ B) = n(A) + n(B) − n(A ∩ B) = 5 + 4 − 2 = 7."),
]


def generate_chapter_mcqs(subject, chapter, notes, count):
    """Generate MCQs strictly from the chosen subject + chapter using local Ollama."""
    if not subject or not chapter:
        raise ValueError("Choose both a subject and a chapter first.")
    notes = (notes or "").strip()
    if not notes:
        notes = "No textbook notes supplied. Use only well-established content that directly belongs to this exact subject and chapter. If you cannot reliably distinguish the chapter's scope, return fewer questions rather than using another chapter."
    prompt = f"""
You are a careful academic MCQ writer for a student's study app.
Generate exactly {count} multiple-choice questions for this precise selection:
SUBJECT: {subject}
CHAPTER: {chapter}

STRICT SCOPE RULES:
- Every question must be directly about the selected subject AND selected chapter.
- Never include questions from another chapter, even if they belong to the same subject.
- Example: Accountancy + Bank Reconciliation Statement must not contain Bills of Exchange questions.
- Use the supplied chapter material as the primary source when present.
- Do not invent textbook-specific facts or claim the questions came from the textbook.
- If the material is insufficient to support {count} reliable questions, return only the number you can support.
- Each question must have exactly four distinct options and exactly one correct answer.
- Include a concise explanation for the correct answer.
- Return ONLY valid JSON in this shape, with no markdown fences:
{{"questions":[{{"question":"...","options":["...","...","...","..."],"answer":0,"explanation":"..."}}]}}
The answer field is the zero-based index (0 to 3) of the correct option.

CHAPTER MATERIAL / NOTES:
{notes[:14000]}
"""
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": [
            {"role": "system", "content": "Follow the requested academic scope exactly. Output valid JSON only."},
            {"role": "user", "content": prompt}
        ], "stream": False, "format": "json", "options": {"temperature": 0.2}},
        timeout=240,
    )
    response.raise_for_status()
    raw = response.json().get("message", {}).get("content", "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The local AI did not return valid MCQ data. Please try again.")
        data = json.loads(raw[start:end + 1])
    questions = data.get("questions", []) if isinstance(data, dict) else []
    valid = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        opts = item.get("options", [])
        ans = item.get("answer")
        explanation = str(item.get("explanation", "")).strip()
        if (q and isinstance(opts, list) and len(opts) == 4 and
            all(isinstance(x, str) and x.strip() for x in opts) and
            isinstance(ans, int) and not isinstance(ans, bool) and 0 <= ans < 4):
            valid.append({"question": q, "options": [x.strip() for x in opts],
                          "answer": ans, "explanation": explanation or "Review the chapter concept and compare each option.",
                          "subject": subject, "chapter": chapter})
    if not valid:
        raise ValueError("The local AI couldn't create any valid questions for that chapter. Add chapter notes and try again.")
    # Keep only the requested chapter-specific set; no fallback to unrelated built-in questions.
    return valid[:count]

def blank():
    return {
        "completed": [], "hours": {}, "journal": {}, "medals": [], "messages": [],
        "results": [], "last_visit": "",
        "profile": {
            "name": "", "share": False, "strong": [], "help": [],
            "greetings": {
                "morning": "Good morning", "afternoon": "Good afternoon",
                "evening": "Good evening", "night": "Good night"
            },
            "goal_hours": 2.0
        },
        "syllabus": {}, "visit_dates": [], "created_at": date.today().isoformat()
    }

def load():
    auth = st.session_state.get(_AUTH_KEY, {})
    user_id = auth.get("user", {}).get("id")
    if SUPABASE_READY and user_id and auth.get("access_token"):
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/learner_progress",
                params={"user_id": f"eq.{user_id}", "select": "data", "limit": "1"},
                headers=_sb_headers(auth["access_token"]), timeout=15)
            r.raise_for_status()
            rows = r.json()
            obj = rows[0]["data"] if rows and isinstance(rows[0].get("data"), dict) else blank()
            had_syllabus = "syllabus" in obj
            for k, v in blank().items(): obj.setdefault(k, v)
            defaults = blank()["profile"]
            if not isinstance(obj.get("profile"), dict): obj["profile"] = defaults.copy()
            for key, value in defaults.items(): obj["profile"].setdefault(key, value)
            if not isinstance(obj["profile"].get("greetings"), dict): obj["profile"]["greetings"] = defaults["greetings"].copy()
            for key, value in defaults["greetings"].items(): obj["profile"]["greetings"].setdefault(key, value)
            if not had_syllabus: obj["syllabus"] = {k: list(v) for k, v in DEFAULT_TOPICS.items()}
            if not obj.get("hours") and isinstance(obj.get("study_hours"), dict): obj["hours"] = obj["study_hours"]
            if not obj.get("results") and isinstance(obj.get("test_results"), list): obj["results"] = obj["test_results"]
            return obj
        except Exception as exc:
            st.error(f"Couldn't load your cloud progress: {exc}")
            st.stop()
    if DATA.exists():
        try:
            obj = json.loads(DATA.read_text(encoding="utf-8"))
            had_syllabus = "syllabus" in obj
            for k, v in blank().items():
                obj.setdefault(k, v)
            defaults = blank()["profile"]
            if not isinstance(obj.get("profile"), dict):
                obj["profile"] = defaults.copy()
            for key, value in defaults.items():
                obj["profile"].setdefault(key, value)
            if not isinstance(obj["profile"].get("greetings"), dict):
                obj["profile"]["greetings"] = defaults["greetings"].copy()
            for key, value in defaults["greetings"].items():
                obj["profile"]["greetings"].setdefault(key, value)
            # Migrate older saved files once; an intentionally emptied syllabus stays empty.
            if not had_syllabus:
                obj["syllabus"] = {k: list(v) for k, v in DEFAULT_TOPICS.items()}
            if not obj.get("hours") and isinstance(obj.get("study_hours"), dict):
                obj["hours"] = obj["study_hours"]
            if not obj.get("results") and isinstance(obj.get("test_results"), list):
                obj["results"] = obj["test_results"]
            return obj
        except (OSError, json.JSONDecodeError):
            st.warning("Saved data could not be read. The file has not been deleted.")
    return blank()

d = load()
# Separate local browser progress by signed-in account, or use a guest key in demo mode.
_auth_user_id = st.session_state.get(_AUTH_KEY, {}).get("user", {}).get("id", "guest")
_browser_state_key = "studybuddy_browser_progress_" + str(_auth_user_id)
try:
    _browser_state = st.session_state.get(_browser_state_key)
    _local_result = LOCAL_STORE(
        data_json=json.dumps(_browser_state if isinstance(_browser_state, dict) else d, ensure_ascii=False),
        storage_key="studybuddy_progress_" + str(_auth_user_id),
        key="studybuddy_local_store")
    if st.session_state.get("studybuddy_browser_loaded_key") != _browser_state_key:
        if isinstance(_local_result, dict) and isinstance(_local_result.get("data"), str):
            _parsed = json.loads(_local_result["data"])
            if isinstance(_parsed, dict):
                d = _parsed
                st.session_state[_browser_state_key] = d
                st.session_state["studybuddy_browser_loaded_key"] = _browser_state_key
        elif isinstance(_browser_state, dict):
            d = _browser_state
            st.session_state["studybuddy_browser_loaded_key"] = _browser_state_key
    elif isinstance(_browser_state, dict):
        d = _browser_state
except Exception:
    # Continue with normal app data if browser storage is unavailable.
    pass
# A local demo directory makes the social UI testable on one computer. Real cross-device
# accounts/chat require a hosted backend; this prototype never pretends these are online users.
DEMO_PEOPLE = [
    {"username":"nova.notes", "name":"Nova Bennett", "bio":"Planner lover · building a steady study streak", "subjects":["Accountancy", "Economics"], "emoji":"🌙"},
    {"username":"orbit.arya", "name":"Arya Sharma", "bio":"Maths practice, clean notes, big goals", "subjects":["Mathematics", "Physics"], "emoji":"🪐"},
    {"username":"kai.learns", "name":"Kai Morgan", "bio":"Curious mind · happy to revise together", "subjects":["Chemistry", "Biology"], "emoji":"🚀"},
    {"username":"luna.library", "name":"Luna Park", "bio":"Flashcards, reading sessions, and calm focus", "subjects":["English", "Economics"], "emoji":"📚"},
    {"username":"atlas.study", "name":"Atlas Reed", "bio":"Break big chapters into small wins", "subjects":["Accountancy", "Mathematics"], "emoji":"🌍"},
    {"username":"mira.focus", "name":"Mira Das", "bio":"Pomodoro fan · consistency over cramming", "subjects":["Physics", "English"], "emoji":"✨"},
]
d.setdefault("network", {"people": [], "sent": [], "incoming": [], "friends": [], "messages": {}})
for key, value in {"people": [], "sent": [], "incoming": [], "friends": [], "messages": {}}.items():
    d["network"].setdefault(key, value)
if not d["network"]["people"]:
    d["network"]["people"] = [dict(x) for x in DEMO_PEOPLE]
d.setdefault("profile", {})
d["profile"].setdefault("username", "")

today = date.today().isoformat()
if d["last_visit"] != today:
    d["last_visit"] = today
if today not in d.setdefault("visit_dates", []):
    d["visit_dates"].append(today)

def all_syllabus_topics():
    return [f"{subject}:{chapter}" for subject, chapters in d.get("syllabus", {}).items() for chapter in chapters]

# 120 collectible medals, with real unlock conditions where practical.
MEDAL_DEFS = []
def add_medals(category, names, desc):
    for i, name in enumerate(names, 1):
        MEDAL_DEFS.append({"name": name, "category": category, "desc": desc.format(n=i), "rarity": ("Legendary" if i % 20 == 0 else "Epic" if i % 10 == 0 else "Rare" if i % 5 == 0 else "Uncommon" if i % 3 == 0 else "Common")})
add_medals("Consistency", [f"Day {i} Devotee" for i in range(1, 21)], "Log study activity on {n} distinct day(s).")
add_medals("Focus", [f"Focus Forge {i}" for i in range(1, 21)], "Accumulate {n} study hour(s) in total.")
add_medals("Syllabus", [f"Chapter Conqueror {i}" for i in range(1, 21)], "Complete {n} syllabus chapter(s).")
add_medals("Arena", [f"Arena Victor {i}" for i in range(1, 21)], "Complete {n} MCQ test(s).")
add_medals("Accuracy", [f"Precision Star {i}" for i in range(1, 21)], "Earn {n} perfect test score(s).")
add_medals("Explorer", [f"Scholar Explorer {i}" for i in range(1, 21)], "Create or maintain {n} subject(s) in your syllabus.")
MEDAL_DEFS += [
 {"name":"Gold","category":"Arena","desc":"Finish a test with zero mistakes.","rarity":"Rare"},
 {"name":"Silver","category":"Arena","desc":"Finish a test with exactly one mistake.","rarity":"Uncommon"},
 {"name":"Bronze","category":"Arena","desc":"Finish a test with two or three mistakes.","rarity":"Common"},
 {"name":"Scholar","category":"Syllabus","desc":"Complete a syllabus chapter.","rarity":"Common"},
 {"name":"Streak Keeper","category":"Consistency","desc":"Maintain a seven-day study streak.","rarity":"Epic"},
 {"name":"Perfectionist","category":"Accuracy","desc":"Earn five perfect test scores.","rarity":"Legendary"},
 {"name":"Imperial Laurel","category":"Rank","desc":"Qualify for the top 10% of a real shared leaderboard.","rarity":"Mythic"},
]


def save():
    st.session_state[_browser_state_key] = d
    auth = st.session_state.get(_AUTH_KEY, {})
    user_id = auth.get("user", {}).get("id")
    if SUPABASE_READY and user_id and auth.get("access_token"):
        try:
            r = requests.post(f"{SUPABASE_URL}/rest/v1/learner_progress",
                params={"on_conflict": "user_id"},
                json={"user_id": user_id, "data": d, "updated_at": datetime.now().astimezone().isoformat()},
                headers=_sb_headers(auth["access_token"], "resolution=merge-duplicates,return=minimal"), timeout=15)
            r.raise_for_status()
        except Exception as exc:
            st.error(f"Cloud save failed; changes may not be synced: {exc}")
    else:
        DATA.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def medal_for(mistakes):
    return "Gold" if mistakes == 0 else "Silver" if mistakes == 1 else "Bronze" if mistakes in (2, 3) else None

def emoji(name):
    return {"Gold":"🥇","Silver":"🥈","Bronze":"🥉","Scholar":"📚","Streak Keeper":"🔥","Perfectionist":"🏆","Imperial Laurel":"👑"}.get(name, "🏅")

all_topics = all_syllabus_topics()
done = len(set(d["completed"]) & set(all_topics))
pct = round(done / max(1, len(all_topics)) * 100)
hours_total = sum(float(v) for v in d["hours"].values())
active_days = len(set(d.get("visit_dates", [])) | set(d["hours"]) | set(d["journal"]) | {r.get("date","") for r in d["results"]} - {""})
tracked = set(d["hours"]) | set(d["journal"])
streak = 0
day = date.today()
while day.isoformat() in tracked:
    streak += 1
    day -= timedelta(days=1)

st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;600;700&display=swap');
:root{--ink:#f3f5ff;--muted:#aab6d7;--cyan:#66e6f5;--violet:#a58cff;--gold:#ffd778;--line:rgba(176,191,255,.2)}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.stApp{position:relative!important;z-index:2!important;background:transparent!important;color:var(--ink)}
body,[data-testid="stAppViewContainer"],[data-testid="stHeader"]{background:transparent!important}
[data-testid="stAppViewContainer"]{position:relative!important;z-index:2!important}
[data-testid="stHeader"]{position:relative!important;z-index:4!important}
.stApp:before,.stApp:after{display:none!important}
@keyframes aurora{from{transform:translate(-2%,-1%) scale(.96)}to{transform:translate(3%,2%) scale(1.08)}}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes shimmer{0%{background-position:-200% center}100%{background-position:200% center}}
@keyframes breathe{0%,100%{box-shadow:0 0 12px #66e6f50b,0 16px 35px #0003}50%{box-shadow:0 0 28px #66e6f526,0 16px 35px #0004}}
@keyframes pop{0%{transform:scale(.7) rotate(-8deg);opacity:0}70%{transform:scale(1.08) rotate(3deg);opacity:1}100%{transform:scale(1);opacity:1}}
[data-testid="stAppViewContainer"]>.main{position:relative;z-index:3}
[data-testid="stAppViewContainer"] .main .block-container{position:relative;z-index:3}
[data-testid="stSidebar"]{isolation:isolate}
[data-testid="stSidebar"]{position:relative;z-index:3}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#101832f5,#0b1021f8);border-right:1px solid var(--line)}
[data-testid="stSidebar"] *{color:var(--ink)}
h1,h2,h3,h4{font-family:'Space Grotesk',sans-serif!important;color:var(--ink)!important;letter-spacing:-.035em}
p,label,[data-testid="stCaptionContainer"]{color:var(--muted)}
.hero{position:relative;overflow:hidden;border:1px solid #aab8ff42;border-radius:26px;padding:28px 30px;margin-bottom:18px;background:linear-gradient(115deg,#6559bd55,#1aa9b329 65%,#151e3ce8);animation:rise .65s ease-out both,breathe 8s ease-in-out infinite}
.hero:after{content:"✦";position:absolute;right:7%;top:15%;font-size:5rem;color:#b9eaff22;animation:float 6s ease-in-out infinite}
@keyframes float{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-12px) rotate(12deg)}}
.eyebrow{font-size:.72rem;letter-spacing:.2em;text-transform:uppercase;font-weight:700;color:var(--cyan)}
.hero-title{font:700 clamp(2rem,4.4vw,3.4rem) 'Space Grotesk',sans-serif;line-height:1.08;margin:.45rem 0;background:linear-gradient(90deg,#fff,#7de9f6,#c4b3ff,#fff);background-size:220% auto;color:transparent;background-clip:text;animation:shimmer 8s linear infinite}
.hero-sub{color:#bdc9e8;font-size:1rem}
[data-testid="stMetric"]{background:linear-gradient(135deg,#273455c9,#131c35d9);border:1px solid var(--line);border-radius:18px;padding:15px;position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
[data-testid="stMetric"]:hover{transform:translateY(-4px);border-color:#66e6f580}
[data-testid="stMetric"]:after{content:"";position:absolute;top:0;left:0;height:2px;width:100%;background:linear-gradient(90deg,transparent,var(--cyan),var(--violet),transparent);background-size:200%;animation:shimmer 5s linear infinite}
[data-testid="stMetricLabel"]{color:var(--muted)!important}[data-testid="stMetricValue"]{color:var(--ink)!important;font-family:'Space Grotesk',sans-serif}
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(135deg,#202d4bc9,#111a32c9);border:1px solid var(--line);border-radius:20px;padding:15px;backdrop-filter:blur(16px);transition:transform .2s,border-color .2s,box-shadow .2s;animation:rise .45s ease-out both}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{transform:translateY(-2px);border-color:#66e6f55c;box-shadow:0 18px 40px #0003,0 0 20px #66e6f50a}
.kicker{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);font-weight:700}
.pill{display:inline-block;border:1px solid #66e6f54d;background:#66e6f510;border-radius:99px;padding:5px 10px;color:var(--cyan);font-size:.74rem;margin:3px}
.stButton>button,.stFormSubmitButton>button{min-height:43px;border-radius:12px;border:1px solid #66e6f55c;background:linear-gradient(110deg,#66e6f522,#a58cff30);color:#f7f8ff;font-weight:700;transition:transform .18s,box-shadow .18s}
.stButton>button:hover,.stFormSubmitButton>button:hover{transform:translateY(-2px);box-shadow:0 0 24px #66e6f522;border-color:var(--cyan);color:white}
.stTextInput input,.stTextArea textarea,.stNumberInput input,[data-baseweb="select"]>div{background:#080d1bc9!important;color:var(--ink)!important;border-color:var(--line)!important;border-radius:11px!important}
.stProgress>div>div>div>div{background:linear-gradient(90deg,var(--cyan),var(--violet));background-size:200%;animation:shimmer 5s linear infinite}
[data-testid="stChatMessage"]{background:#1b2846b5;border:1px solid var(--line);border-radius:16px;animation:rise .25s ease-out}
.medal{border:1px solid var(--line);border-radius:17px;text-align:center;padding:16px;background:#202d4b9c;animation:pop .55s ease-out both}
.medal .icon{font-size:2.2rem;filter:drop-shadow(0 0 9px #ffd77840)}
/* Extra motion layer: drifting ambient particles and pointer-reactive glass cards */
@keyframes particleDrift{0%{background-position:0 0,0 0,0 0;transform:translate3d(0,0,0)}50%{background-position:90px -120px,-70px 100px,45px -65px;transform:translate3d(0,-7px,0)}100%{background-position:180px -240px,-140px 200px,90px -130px;transform:translate3d(0,0,0)}}
@keyframes sparklePulse{0%,100%{opacity:.18}50%{opacity:.72}}
.stApp:after{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.58;background-image:radial-gradient(2px 2px at 20px 30px,#b8f7ff9c 99%,transparent),radial-gradient(1.5px 1.5px at 140px 80px,#d8c8ffb0 99%,transparent),radial-gradient(1px 1px at 70px 160px,#ffffff9c 99%,transparent);background-size:220px 220px,280px 280px,170px 170px;animation:particleDrift 28s linear infinite,sparklePulse 7s ease-in-out infinite alternate}
div[data-testid="stVerticalBlockBorderWrapper"]{transform-origin:center;transition:transform .32s cubic-bezier(.2,.8,.2,1),border-color .3s,box-shadow .3s;will-change:transform}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{transform:translateY(-7px) scale(1.025);border-color:#66e6f5a6;box-shadow:0 24px 55px #0005,0 0 30px #66e6f525}
[data-testid="stMetric"]{transition:transform .32s cubic-bezier(.2,.8,.2,1),border-color .3s,box-shadow .3s}
[data-testid="stMetric"]:hover{transform:translateY(-7px) scale(1.045);border-color:#66e6f5a6;box-shadow:0 18px 38px #0004,0 0 28px #66e6f51c}
.stButton>button,.stFormSubmitButton>button{transition:transform .24s cubic-bezier(.2,.8,.2,1),box-shadow .24s,border-color .24s}
.stButton>button:hover,.stFormSubmitButton>button:hover{transform:translateY(-3px) scale(1.025);box-shadow:0 9px 24px #66e6f526,0 0 22px #a58cff18}
@media(prefers-reduced-motion:reduce){.stApp:after{animation:none!important}*,*:before,*:after{transition-duration:.01ms!important;animation-duration:.01ms!important;animation-iteration-count:1!important}}
@media(max-width:700px){.hero{padding:20px 17px;border-radius:19px}.hero:after{right:3%;font-size:3rem}[data-testid="stMetric"]{padding:10px}div[data-testid="stVerticalBlockBorderWrapper"]{padding:11px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}

/* StudyBuddy motion system: whole-screen atmosphere, navigation and glass interactions */
@keyframes screenEnter{from{opacity:.25;transform:translateY(12px) scale(.995);filter:blur(3px)}to{opacity:1;transform:none;filter:blur(0)}}
@keyframes navGlow{0%,100%{box-shadow:0 0 0 #66e6f500}50%{box-shadow:0 0 24px #66e6f525}}
@keyframes orbit{from{transform:rotate(0deg) translateX(9px) rotate(0deg)}to{transform:rotate(360deg) translateX(9px) rotate(-360deg)}}
@keyframes pageLine{0%{transform:scaleX(0);opacity:0}35%{opacity:1}100%{transform:scaleX(1);opacity:0}}
.stApp{background-attachment:fixed!important}
[data-testid="stAppViewContainer"] .main .block-container{animation:screenEnter .55s cubic-bezier(.2,.8,.2,1) both;max-width:1500px;padding-top:1.5rem;padding-bottom:3rem}
[data-testid="stSidebar"]{background:linear-gradient(160deg,#111d3af7,#11132af5 55%,#091421f7)!important;box-shadow:12px 0 50px #0002;position:relative}
[data-testid="stSidebar"]:after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 20% 10%,#66e6f51c,transparent 28%),radial-gradient(circle at 85% 65%,#a58cff18,transparent 30%);background-size:150% 150%;animation:aurora 16s ease-in-out infinite alternate}
[data-testid="stSidebar"] [role="radiogroup"] label{border:1px solid transparent!important;border-radius:12px;padding:8px 10px!important;margin:3px 0!important;transition:all .25s cubic-bezier(.2,.8,.2,1)!important}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#66e6f51b!important;border-color:#66e6f55c!important;transform:translateX(5px) scale(1.015);box-shadow:0 0 18px #66e6f51c}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:linear-gradient(100deg,#66e6f52a,#a58cff22)!important;border-color:#66e6f57a!important;box-shadow:0 0 20px #66e6f522;animation:navGlow 3s ease-in-out infinite}
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stMetric"], .hero, .medal{transform-origin:center;will-change:transform;transition:transform .28s cubic-bezier(.2,.8,.2,1),box-shadow .28s,border-color .28s,filter .28s!important}
[data-testid="stVerticalBlockBorderWrapper"]:hover{transform:translateY(-6px) scale(1.018)!important;box-shadow:0 24px 52px #0005,0 0 28px #66e6f51a!important;filter:saturate(1.12)}
[data-testid="stMetric"]:hover{transform:translateY(-7px) scale(1.04)!important;box-shadow:0 20px 40px #0004,0 0 26px #66e6f528}
.medal:hover{transform:translateY(-6px) scale(1.035)!important;box-shadow:0 0 32px #ffd77825;filter:brightness(1.12)}
.hero:hover{border-color:#66e6f580;box-shadow:0 20px 60px #0004,0 0 35px #66e6f514}
.stTabs [data-baseweb="tab"]{transition:all .25s ease;border-radius:10px}
.stTabs [data-baseweb="tab"]:hover{background:#66e6f51c;transform:translateY(-2px)}
.stButton>button:active,.stFormSubmitButton>button:active{transform:scale(.97)!important}
.stProgress>div>div>div>div{transition:width .8s cubic-bezier(.2,.8,.2,1)!important}
.buddy-card{position:relative;display:flex;gap:16px;align-items:center;padding:18px;border:1px solid #66e6f544;border-radius:18px;background:linear-gradient(125deg,#16284bc9,#18203dc9);overflow:hidden}
.buddy-face{font-size:3.2rem;line-height:1;filter:drop-shadow(0 0 13px #66e6f54c);animation:bob 3s ease-in-out infinite;display:inline-block}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
.greeting{border:1px solid #a58cff4a;border-radius:18px;padding:17px;background:linear-gradient(125deg,#a58cff20,#66e6f516,#16213dc9);animation:rise .7s ease both}
@media(max-width:700px){[data-testid="stAppViewContainer"] .main .block-container{padding-left:1rem;padding-right:1rem}.hero{padding:20px 16px}.buddy-card{padding:13px}.buddy-face{font-size:2.6rem}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}


/* Photographic HD galaxy background with slow cinematic motion. */
#studybuddy-galaxy-photo{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0!important;background:#02030b}
#studybuddy-galaxy-photo:before{content:"";position:absolute;inset:-7%;background-image:linear-gradient(180deg,rgba(2,4,14,.36),rgba(2,4,14,.58)),url('https://images.unsplash.com/photo-1462331940025-496dfbfc7564?auto=format&fit=crop&w=2560&q=90');background-size:cover;background-position:center center;background-repeat:no-repeat;transform-origin:center;animation:galaxyKenBurns 72s ease-in-out infinite alternate;will-change:transform}
#studybuddy-galaxy-photo:after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 22%,rgba(0,0,8,.34) 100%),linear-gradient(90deg,rgba(1,3,12,.25),transparent 48%,rgba(1,3,12,.22));}
@keyframes galaxyKenBurns{0%{transform:scale(1.02) translate3d(-.5%,.2%,0)}100%{transform:scale(1.16) translate3d(.7%,-.6%,0)}}
.galaxy-canvas{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:0!important;display:block;opacity:.52}
@media(prefers-reduced-motion:reduce){#studybuddy-galaxy-photo:before{animation:none;transform:scale(1.04)}.galaxy-canvas{opacity:.5}}

/* Responsive, scroll-linked galaxy scenery. Layers remain behind all controls. */
.space-scene{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;isolation:isolate;contain:layout paint}
.space-layer{position:absolute;pointer-events:none;will-change:opacity,transform;transform-origin:center center}
.space-moon{width:clamp(165px,24vw,315px);aspect-ratio:1;right:clamp(-55px,2vw,28px);top:clamp(42px,7vh,82px);opacity:1;filter:brightness(1.22) drop-shadow(0 0 26px #d9edff99) drop-shadow(0 0 64px #b4d5ff55);animation:moonDrift 12s ease-in-out infinite alternate}
.space-asteroids{inset:0;opacity:.0;animation:asteroidCruise 24s ease-in-out infinite}
.space-asteroids:before{content:"";position:absolute;left:-12%;top:43%;width:124%;height:clamp(100px,18vh,230px);transform:rotate(-12deg);background:radial-gradient(ellipse at 50% 50%,#b7c8ed14,transparent 68%)}
.rock{position:absolute;border-radius:42% 58% 53% 47%;background:radial-gradient(circle at 28% 22%,#b7b9c8,#59627b 35%,#252e43 72%,#111827);box-shadow:inset -8px -7px 12px #060a14aa,0 0 14px #9bb6ed16}
.space-earth{width:clamp(340px,55vw,720px);aspect-ratio:1;left:clamp(-180px,-5vw,-45px);bottom:clamp(-240px,-17vw,-90px);opacity:.94;filter:drop-shadow(0 0 18px #40aaff88) drop-shadow(0 0 70px #2477ff55);animation:earthDrift 16s ease-in-out infinite alternate}
@keyframes moonScroll{0%,12%{opacity:1;transform:translate3d(0,0,0) scale(1)}32%{opacity:0;transform:translate3d(8vw,-7vh,0) scale(.88)}100%{opacity:0;transform:translate3d(8vw,-7vh,0) scale(.88)}}
@keyframes asteroidScroll{0%,18%{opacity:0;transform:translate3d(0,7vh,0)}35%,49%{opacity:1;transform:translate3d(0,0,0)}70%,100%{opacity:0;transform:translate3d(0,-8vh,0)}}
@keyframes earthScroll{0%,48%{opacity:0;transform:translate3d(-3vw,8vh,0) scale(.94)}72%,100%{opacity:1;transform:translate3d(0,0,0) scale(1)}}
@keyframes moonDrift{0%{translate:0 0;rotate:-2deg;filter:brightness(1.08) drop-shadow(0 0 22px #d9edff66)}100%{translate:-18px 14px;rotate:2deg;filter:brightness(1.3) drop-shadow(0 0 38px #d9edffbb)}}
@keyframes asteroidCruise{0%,100%{translate:-2vw 1vh;opacity:.10}25%,75%{opacity:.58}50%{translate:2vw -2vh;opacity:.88}}
@keyframes earthDrift{0%{translate:0 0}100%{translate:10px -14px}}
@keyframes satelliteOrbit{from{transform:translate(-50%,-50%) rotate(0deg)}to{transform:translate(-50%,-50%) rotate(360deg)}}
@keyframes moonSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes earthSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.space-satellite-orbit{position:absolute;left:40%;top:30%;width:44%;height:44%;max-width:180px;max-height:180px;transform:translate(-50%,-50%);border:1px solid #c9eaff24;border-radius:50%;animation:satelliteOrbit 24s linear infinite;box-sizing:border-box;will-change:transform;overflow:visible}
.space-satellite{position:absolute;left:0;top:50%;width:clamp(13px,1.5vw,20px);height:clamp(9px,1vw,14px);background:linear-gradient(110deg,#f5fbff 0%,#8fa7c8 45%,#dceaff 100%);border:1px solid #d8edff;border-radius:2px;box-shadow:0 0 12px #7cc8ff88;transform:translate(-50%,-50%);z-index:2}.space-satellite:before,.space-satellite:after{content:"";position:absolute;top:1px;width:9px;height:7px;background:repeating-linear-gradient(90deg,#25548e 0 2px,#6eafe8 2px 4px);border:1px solid #a8dfff;left:-10px;box-sizing:border-box}.space-satellite:after{left:auto;right:-10px}.space-moon svg{transform-origin:50% 50%;animation:moonSpin 85s linear infinite}.space-earth>svg{transform-origin:50% 50%;animation:earthSpin 110s linear infinite}.space-earth{overflow:visible}
.space-satellite:before,.space-satellite:after{content:"";position:absolute;top:2px;width:9px;height:7px;background:#3d75b8;border:1px solid #9ed9ff;left:-9px}.space-satellite:after{left:auto;right:-9px}
/* Scroll progress is driven by a parent-document listener below; no CSS scroll-timeline dependency. */
@media(max-width:700px){.space-moon{width:clamp(145px,34vw,225px);right:-28px;top:86px}.space-earth{width:clamp(300px,80vw,470px);left:-110px;bottom:-110px}.space-earth .space-satellite-orbit{left:47%;top:27%;width:44%;height:44%;max-width:135px;max-height:135px}.space-earth .space-satellite{width:14px;height:10px}.space-earth .space-satellite:before,.space-earth .space-satellite:after{width:7px;height:7px;left:-8px}.space-earth .space-satellite:after{left:auto;right:-8px}.space-asteroids:before{top:48%;height:120px}.rock{box-shadow:inset -4px -4px 7px #060a14aa,0 0 8px #9bb6ed12}}
@media(prefers-reduced-motion:reduce){.space-layer,.space-satellite-orbit,.space-moon svg,.space-earth>svg{animation:none!important}.space-moon{opacity:.25}.space-asteroids{opacity:.12}.space-earth{opacity:.88}}


/* Photographic planetary surfaces: textured spheres instead of illustrated SVGs. */
.space-moon,.space-earth{isolation:isolate;overflow:visible!important}
.space-moon>svg,.space-earth>svg{display:none!important}
.space-moon:before,.space-earth:before{content:"";position:absolute;inset:0;border-radius:50%;display:block;background-repeat:repeat-x;background-size:200% 100%;animation:planetTextureSpin 90s linear infinite;box-shadow:inset -24px -12px 45px #02040dcc,inset 10px 6px 22px #ffffff24,0 0 30px #9bcfff28}
.space-moon:before{background-image:url('https://threejs.org/examples/textures/planets/moon_1024.jpg');background-size:200% 100%;filter:grayscale(.25) contrast(1.12) brightness(.88);box-shadow:inset -30px -14px 48px #02040ddd,inset 8px 4px 22px #ffffff28,0 0 24px #b9d5ff38}
.space-earth:before{background-image:url('https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg');background-size:200% 100%;filter:saturate(1.45) contrast(1.16) brightness(1.04);box-shadow:inset -35px -14px 52px #010717cc,inset 9px 5px 25px #b8edff35,0 0 0 2px #70cfff88,0 0 34px #168bff88}
@keyframes planetTextureSpin{from{background-position:0% 50%}to{background-position:200% 50%}}
/* Irregular, photo-textured rocks with no cartoon outlines. */
.rock{border-radius:38% 62% 57% 43%!important;background-image:linear-gradient(135deg,#aab0ba44,#080b13b8),url('https://threejs.org/examples/textures/planets/moon_1024.jpg')!important;background-size:cover,220% 120%!important;background-position:center,center!important;filter:contrast(1.18) saturate(.35);box-shadow:inset -12px -8px 15px #02040ddd, inset 3px 2px 5px #dce4f333,0 2px 8px #0009!important}
.space-asteroids{filter:contrast(1.1)}
.space-satellite-orbit{border-color:#c9eaff12!important}
.space-satellite{background:linear-gradient(135deg,#f8faff,#8995a7 48%,#e5edf8)!important;box-shadow:0 0 8px #7cc8ff66!important}
@media(max-width:700px){.space-moon:before,.space-earth:before{box-shadow:inset -18px -8px 30px #02040ddd,0 0 20px #168bff44}}


</style>
""", unsafe_allow_html=True)


# Lightweight, responsive galaxy background. It draws directly on the parent page so it
# remains fixed behind the UI, reacts to pointer/scroll, and needs no external textures.
components.html(r"""<script>
(() => {
  let doc, win;
  try { doc = window.parent.document; win = window.parent; } catch (e) { return; }
  if (!doc) return;
  if (!doc.getElementById('studybuddy-galaxy-photo')) {
    const photo = doc.createElement('div');
    photo.id = 'studybuddy-galaxy-photo';
    photo.setAttribute('aria-hidden', 'true');
    (doc.body || doc.documentElement).appendChild(photo);
  }
  if (doc.getElementById('studybuddy-galaxy-canvas')) return;
  const canvas = doc.createElement('canvas');
  canvas.id = 'studybuddy-galaxy-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:0;opacity:.52;display:block;';
  (doc.body || doc.documentElement).appendChild(canvas);
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;
  const reduced = win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 1, h = 1, dpr = 1, stars = [], shooting = [], pointerX = 0, pointerY = 0;
  let scrollProgress = 0, lastShot = 0, lastTime = 0, raf = 0;
  const rand = (a,b) => a + Math.random() * (b-a);
  function resize() {
    w = Math.max(1, win.innerWidth || 1); h = Math.max(1, win.innerHeight || 1);
    dpr = Math.min(win.devicePixelRatio || 1, 1.6);
    canvas.width = Math.round(w*dpr); canvas.height = Math.round(h*dpr);
    canvas.style.width = w+'px'; canvas.style.height = h+'px';
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const count = Math.max(65, Math.min(175, Math.floor(w*h/8500)));
    stars = Array.from({length:count}, () => ({x:rand(0,w),y:rand(0,h),r:rand(.35,1.55),a:rand(.22,.85),tw:rand(.4,1.7),phase:rand(0,Math.PI*2),depth:rand(.25,1)}));
  }
  function readScroll() {
    const root = doc.scrollingElement || doc.documentElement;
    const max = Math.max(1, root.scrollHeight - root.clientHeight);
    scrollProgress = Math.max(0, Math.min(1, (win.scrollY || root.scrollTop || 0) / max));
  }
  function onPointer(e) { pointerX = ((e.clientX / Math.max(1,w))-.5); pointerY = ((e.clientY / Math.max(1,h))-.5); }
  function nebula(x,y,r,c1,c2,dx,dy) {
    const g = ctx.createRadialGradient(x+dx,y+dy,0,x+dx,y+dy,r);
    g.addColorStop(0,c1); g.addColorStop(1,c2);
    ctx.fillStyle=g; ctx.fillRect(0,0,w,h);
  }
  function drawSpiralGalaxy(now) {
    // A soft, diagonal spiral galaxy gives the starfield a recognizable galaxy shape.
    const cx = w * .51 + Math.sin(now * .000035) * w * .018 - pointerX * 10;
    const cy = h * .48 + Math.cos(now * .00003) * h * .018 - pointerY * 8 + scrollProgress * 14;
    const rx = Math.min(w * .47, h * .82);
    const ry = Math.min(h * .29, w * .22);
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-.34);
    const core = ctx.createRadialGradient(0, 0, 0, 0, 0, rx * .58);
    core.addColorStop(0, 'rgba(211,205,255,.16)');
    core.addColorStop(.15, 'rgba(139,139,255,.10)');
    core.addColorStop(.48, 'rgba(96,91,206,.045)');
    core.addColorStop(1, 'rgba(42,57,115,0)');
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.ellipse(0, 0, rx * .9, ry * 1.05, 0, 0, Math.PI * 2); ctx.fill();
    for (let arm = 0; arm < 2; arm++) {
      ctx.save();
      ctx.rotate(arm * Math.PI + (reduced ? 0 : now * .000012));
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const t = i / 120;
        const angle = .25 + t * Math.PI * 2.25;
        const radius = 4 + t * rx * .86;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius * (ry / Math.max(1, rx));
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = arm === 0 ? 'rgba(117,151,255,.10)' : 'rgba(101,224,255,.075)';
      ctx.lineWidth = Math.max(5, ry * .13);
      ctx.lineCap = 'round';
      ctx.shadowBlur = 22;
      ctx.shadowColor = arm === 0 ? 'rgba(126,119,255,.18)' : 'rgba(79,212,255,.15)';
      ctx.stroke();
      ctx.restore();
    }
    ctx.restore();
  }
  function frame(now) {
    if (!doc.documentElement.contains(canvas)) { (doc.body || doc.documentElement).appendChild(canvas); }
    const dt = Math.min(32, now-(lastTime||now)); lastTime=now;
    ctx.clearRect(0,0,w,h);
    const drift = reduced ? 0 : now*.003;
    // The galaxy itself is now a high-resolution photographic image; this canvas only adds subtle stars and shooting stars.
    // Do not draw procedural spiral arms or gradient nebulae over the real image.
    for (const s of stars) {
      const twinkle = reduced ? 1 : (.72 + .28*Math.sin(now*.001*s.tw+s.phase));
      const px = ((s.x + (reduced?0:pointerX*s.depth*20) + w*2)%(w+20))-10;
      const py = ((s.y + (reduced?0:pointerY*s.depth*14) + scrollProgress*s.depth*85 + h*2)%(h+20))-10;
      ctx.globalAlpha=s.a*twinkle; ctx.fillStyle=s.r>1.2?'#dceaff':'#b9d9ff';
      ctx.beginPath(); ctx.arc(px,py,s.r,0,Math.PI*2); ctx.fill();
      if(s.r>1.35){ctx.globalAlpha*=.4;ctx.fillRect(px-3,py-.35,6,.7);ctx.fillRect(px-.35,py-3,.7,6);}
    }
    ctx.globalAlpha=1;
    if (!reduced && now-lastShot>rand(3400,6500)) {
      lastShot=now;
      if(shooting.length<1) shooting.push({x:rand(w*.1,w*.85),y:rand(0,h*.45),vx:rand(5,8),vy:rand(2,4),life:0,max:rand(22,36)});
    }
    for(let i=shooting.length-1;i>=0;i--){
      const q=shooting[i]; q.x+=q.vx*(dt/16); q.y+=q.vy*(dt/16); q.life+=dt/16;
      const alpha=Math.max(0,1-q.life/q.max); const g=ctx.createLinearGradient(q.x-q.vx*8,q.y-q.vy*8,q.x,q.y);
      g.addColorStop(0,'rgba(130,190,255,0)');g.addColorStop(1,'rgba(220,242,255,'+alpha+')');
      ctx.strokeStyle=g;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(q.x-q.vx*9,q.y-q.vy*9);ctx.lineTo(q.x,q.y);ctx.stroke();
      if(q.life>q.max||q.x>w+30||q.y>h+30)shooting.splice(i,1);
    }
    ctx.globalAlpha=1;
    if (!reduced) raf=win.requestAnimationFrame(frame);
  }
  resize(); readScroll();
  win.addEventListener('resize',resize,{passive:true});
  win.addEventListener('scroll',readScroll,{passive:true});
  doc.addEventListener('pointermove',onPointer,{passive:true});
  if (reduced) frame(0); else raf=win.requestAnimationFrame(frame);
  // Streamlit may rebuild parts of the DOM on reruns; preserve the same canvas layer.
  const observer = new MutationObserver(() => {
    if(!doc.documentElement.contains(doc.getElementById('studybuddy-galaxy-photo'))) { const photo=doc.createElement('div'); photo.id='studybuddy-galaxy-photo'; photo.setAttribute('aria-hidden','true'); (doc.body || doc.documentElement).appendChild(photo); }
    if(!doc.documentElement.contains(canvas)) (doc.body || doc.documentElement).appendChild(canvas);
  });
  observer.observe(doc.documentElement,{childList:true,subtree:true});
})();
</script>""", height=0, scrolling=False)


# Persistent galaxy scenery; CSS scroll timelines transition moon -> asteroids -> Earth.
st.markdown(r'''<div class="space-scene" aria-hidden="true">
  <div class="space-layer space-moon">
    <svg viewBox="0 0 420 420" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="moonSurface" cx="30%" cy="24%" r="78%"><stop offset="0" stop-color="#fff"/><stop offset=".28" stop-color="#e7edf5"/><stop offset=".62" stop-color="#aeb9c9"/><stop offset=".86" stop-color="#68758b"/><stop offset="1" stop-color="#303b50"/></radialGradient>
        <radialGradient id="moonShade" cx="28%" cy="24%" r="76%"><stop offset=".55" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#080d1b" stop-opacity=".65"/></radialGradient>
        <clipPath id="moonClip"><circle cx="210" cy="210" r="194"/></clipPath>
      </defs>
      <circle cx="210" cy="210" r="202" fill="#dcecff" opacity=".10"/>
      <circle cx="210" cy="210" r="194" fill="url(#moonSurface)"/>
      <g clip-path="url(#moonClip)" fill="#647187" opacity=".38">
        <circle cx="112" cy="102" r="27"/><circle cx="112" cy="102" r="19" fill="#dce3ed" opacity=".7"/><circle cx="270" cy="91" r="19"/><circle cx="270" cy="91" r="12" fill="#e7edf5" opacity=".8"/>
        <circle cx="306" cy="180" r="34"/><circle cx="306" cy="180" r="25" fill="#e4eaf2" opacity=".7"/><circle cx="183" cy="216" r="42"/><circle cx="183" cy="216" r="32" fill="#dfe6ef" opacity=".65"/>
        <circle cx="90" cy="270" r="18"/><circle cx="90" cy="270" r="12" fill="#dfe6ef"/><circle cx="263" cy="304" r="25"/><circle cx="263" cy="304" r="18" fill="#e3eaf2"/><circle cx="337" cy="270" r="13"/><circle cx="151" cy="55" r="9"/><circle cx="228" cy="142" r="10"/><circle cx="129" cy="330" r="11"/><circle cx="350" cy="112" r="8"/>
      </g>
      <g fill="none" stroke="#f8fbff" stroke-opacity=".35" stroke-width="3"><circle cx="112" cy="102" r="27"/><circle cx="306" cy="180" r="34"/><circle cx="183" cy="216" r="42"/><circle cx="263" cy="304" r="25"/></g>
      <circle cx="210" cy="210" r="194" fill="url(#moonShade)"/>
    </svg>
  </div>
  <div class="space-layer space-asteroids">
    <span class="rock" style="width:44px;height:33px;left:4%;top:39%;transform:rotate(28deg)"></span><span class="rock" style="width:25px;height:21px;left:13%;top:57%;transform:rotate(-14deg)"></span><span class="rock" style="width:62px;height:46px;left:22%;top:43%;transform:rotate(12deg)"></span><span class="rock" style="width:18px;height:15px;left:29%;top:63%;transform:rotate(33deg)"></span><span class="rock" style="width:34px;height:28px;left:37%;top:37%;transform:rotate(-22deg)"></span><span class="rock" style="width:50px;height:37px;left:45%;top:55%;transform:rotate(17deg)"></span><span class="rock" style="width:22px;height:19px;left:52%;top:41%;transform:rotate(52deg)"></span><span class="rock" style="width:70px;height:49px;left:59%;top:59%;transform:rotate(-18deg)"></span><span class="rock" style="width:30px;height:23px;left:68%;top:36%;transform:rotate(11deg)"></span><span class="rock" style="width:45px;height:35px;left:75%;top:53%;transform:rotate(-32deg)"></span><span class="rock" style="width:20px;height:17px;left:82%;top:40%;transform:rotate(21deg)"></span><span class="rock" style="width:56px;height:42px;left:89%;top:59%;transform:rotate(7deg)"></span><span class="rock" style="width:14px;height:12px;left:95%;top:34%"></span><span class="rock" style="width:12px;height:10px;left:7%;top:68%"></span><span class="rock" style="width:16px;height:13px;left:33%;top:33%"></span><span class="rock" style="width:13px;height:11px;left:64%;top:69%"></span><span class="rock" style="width:16px;height:13px;left:85%;top:69%"></span>
  </div>
  <div class="space-layer space-earth">
    <svg viewBox="0 0 440 440" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <defs><radialGradient id="earthOcean" cx="28%" cy="23%" r="80%"><stop offset="0" stop-color="#5bd7ff"/><stop offset=".32" stop-color="#1678d7"/><stop offset=".7" stop-color="#0750a4"/><stop offset="1" stop-color="#071b54"/></radialGradient><radialGradient id="earthShade" cx="28%" cy="22%" r="80%"><stop offset=".55" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#020818" stop-opacity=".65"/></radialGradient><clipPath id="earthClip"><circle cx="220" cy="220" r="198"/></clipPath><filter id="cloudBlur"><feGaussianBlur stdDeviation="2.5"/></filter></defs>
      <circle cx="220" cy="220" r="207" fill="#49baff" opacity=".17"/><circle cx="220" cy="220" r="198" fill="#53bfff" opacity=".25"/><circle cx="220" cy="220" r="190" fill="url(#earthOcean)"/>
      <g clip-path="url(#earthClip)">
        <path d="M58 107 L91 80 127 84 145 110 176 119 185 147 163 169 172 197 147 219 132 251 111 263 96 235 74 218 65 180 44 152Z" fill="#55a95f"/><path d="M150 226 L181 219 204 240 214 274 198 314 185 353 163 329 157 292 139 269Z" fill="#3c9a58"/><path d="M218 91 L252 75 283 88 306 108 330 111 348 136 330 160 299 161 281 181 255 170 242 143 216 131Z" fill="#63b66c"/><path d="M259 190 L289 183 315 199 327 226 313 254 298 286 276 296 259 266 244 242Z" fill="#419b57"/><path d="M337 290 L357 280 379 297 370 322 348 329 334 310Z" fill="#62ad5c"/>
        <g fill="#eaf8ff" opacity=".82" filter="url(#cloudBlur)"><path d="M43 127q20-22 40-3t42 1q18-11 29 8t-18 21q-25-8-43 4t-43-3q-23-9-7-28Z"/><path d="M173 102q18-18 37-2t28 0q22-9 30 12t-20 17q-21-8-36 5t-32-6q-19-12-7-26Z"/><path d="M255 207q19-22 37-3t35 2q19-7 24 12t-22 17q-21-8-36 4t-31-7q-18-11-7-25Z"/><path d="M87 289q17-18 34-3t31 1q17-8 23 11t-20 16q-18-7-31 4t-28-6q-17-10-9-23Z"/><path d="M301 129q14-14 27-1t22 1q15-6 20 9t-16 12q-16-6-27 3t-22-5q-13-8-4-19Z"/></g>
        <g fill="none" stroke="#d9f5ff" stroke-opacity=".38" stroke-width="3"><path d="M38 160q40-20 72 0t65-2"/><path d="M184 88q33 13 54 0t51 7"/><path d="M248 248q36-18 66 2t48-3"/></g>
      </g><circle cx="220" cy="220" r="190" fill="url(#earthShade)"/><circle cx="220" cy="220" r="193" fill="none" stroke="#6ccfff" stroke-width="4" stroke-opacity=".8"/>
    </svg>
    <div class="space-satellite-orbit"><span class="space-satellite"></span></div>
  </div>
</div>''', unsafe_allow_html=True)

# Real scroll-linked animation: listen to the actual Streamlit page scroller in the parent document.
# This works even when the browser does not support CSS animation-timeline: scroll().
components.html(r"""<script>
(() => {
  let doc;
  try { doc = window.parent.document; } catch (e) { return; }
  const update = () => {
    try {
      const scene = doc.querySelector('.space-scene');
      if (!scene) return;
      const candidates = [doc.scrollingElement, doc.documentElement, doc.body,
        ...doc.querySelectorAll('[data-testid="stAppViewContainer"], section.main, .main, [data-testid="stMain"]')].filter(Boolean);
      let top = 0, max = 0;
      for (const el of candidates) {
        const range = Math.max(0, el.scrollHeight - el.clientHeight);
        const current = el === doc.scrollingElement || el === doc.documentElement || el === doc.body
          ? (doc.defaultView?.scrollY || el.scrollTop || 0) : (el.scrollTop || 0);
        if (range > max) { max = range; top = current; }
        if (current > 0 && current >= top) top = current;
      }
      if (max <= 0) max = Math.max(1, doc.documentElement.scrollHeight - doc.documentElement.clientHeight);
      const p = Math.max(0, Math.min(1, top / max));
      const moon = scene.querySelector('.space-moon');
      const rocks = scene.querySelector('.space-asteroids');
      const earth = scene.querySelector('.space-earth');
      const mix = (a,b,t) => a + (b-a)*t;
      const clamp = (v,a=0,b=1) => Math.max(a,Math.min(b,v));
      const fade = (v,a,b) => clamp((v-a)/(b-a));
      if (moon) {
        const gone = fade(p,.08,.34);
        /* opacity stays CSS-animated as a visible fallback; movement still reacts to scroll */
        moon.style.transform = `translate3d(${gone*5}vw,${-gone*5}vh,0) scale(${1-gone*.12})`;
      }
      if (rocks) {
        const appear = fade(p,.18,.38), disappear = 1-fade(p,.54,.76);
        const visible = appear*disappear;
        /* CSS animation keeps asteroids visible even if Streamlit's scroll container is unusual */
        rocks.style.transform = `translate3d(0,${mix(7,-5,p)}vh,0)`;
      }
      if (earth) {
        const arrive = fade(p,.48,.76);
        /* Keep Earth vivid and visible; scroll changes its position and scale */
        earth.style.transform = `translate3d(${-3*(1-arrive)}vw,${8*(1-arrive)}vh,0) scale(${.94+.06*arrive})`;
      }
    } catch (e) { /* Keep the static scene if the host browser restricts parent access. */ }
  };
  try {
    const doc = window.parent.document;
    const nodes = [doc.defaultView, doc.scrollingElement, doc.documentElement, doc.body,
      ...doc.querySelectorAll('[data-testid="stAppViewContainer"], section.main, .main, [data-testid="stMain"]')].filter(Boolean);
    nodes.forEach(node => node.addEventListener('scroll', update, {passive:true}));
    doc.defaultView?.addEventListener('resize', update, {passive:true});
    const observer = new MutationObserver(update);
    observer.observe(doc.body, {childList:true,subtree:true});
    update();
    setTimeout(update, 120);
    setTimeout(update, 600);
  } catch (e) { }
})();
</script>""", height=0, scrolling=False)


def hero(k, title, subtitle):
    st.markdown(f'<div class="hero"><div class="eyebrow">{k}</div><div class="hero-title">{title}</div><div class="hero-sub">{subtitle}</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("# ✦ StudyBuddy")
    st.caption("THE SCHOLAR'S QUEST")
    st.markdown('<span class="pill">LOCAL AI</span><span class="pill">QUEST MODE</span>', unsafe_allow_html=True)
    page = st.radio("YOUR SPACE", ["Overview", "Syllabus", "Study Journal", "MCQ Arena", "Medal Cabinet", "Scholar Network", "Global Lobby", "Talk to Your Mates"])
    st.markdown("---")
    st.markdown("### 😄 Buddy")
    st.caption("Your study companion is ready.")
    if SUPABASE_READY and st.session_state.get(_AUTH_KEY, {}).get("access_token"):
        if st.button("Log out", use_container_width=True):
            st.session_state.pop(_AUTH_KEY, None)
            st.rerun()
    components.html("""<div id='buddy' style='font:600 13px system-ui;color:#dce9ff;text-align:center;padding:10px;border:1px solid #66e6f544;border-radius:16px;background:linear-gradient(135deg,#1a2b4c,#151a34)'><div id='face' style='font-size:48px;transition:transform .12s'>😄</div><div id='mood' style='color:#76eaff;margin-top:5px'>READY TO LEARN</div><div style='font-size:11px;color:#9eafd2;margin-top:4px'>Move your pointer around me!</div></div><script>const b=document.getElementById('buddy'),f=document.getElementById('face'),m=document.getElementById('mood');let last=0;b.addEventListener('mousemove',e=>{const r=b.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;f.style.transform=`translate(${x*10}px,${y*7}px) rotate(${x*7}deg)`;m.textContent=x<-.18?'LOOKING LEFT':x>.18?'LOOKING RIGHT':y<-.12?'LOOKING UP':'FOLLOWING YOU'});b.addEventListener('mouseleave',()=>{f.style.transform='';m.textContent='READY TO LEARN'});b.addEventListener('click',()=>{f.textContent='🤩';m.textContent='LET’S GO!';setTimeout(()=>{f.textContent='😄';m.textContent='READY TO LEARN'},1100)});</script>""",height=150, scrolling=False)

if page == "Overview":
    hero("YOUR PERSONAL SCHOLAR SPACE", "Make progress legendary.", "Every topic cleared is XP earned. Every study session moves you forward.")
    profile = d.setdefault("profile", blank()["profile"])
    greeting_defaults = blank()["profile"]["greetings"]
    profile.setdefault("greetings", greeting_defaults.copy())
    profile.setdefault("goal_hours", 2.0)
    local_hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour
    time_key = "morning" if 5 <= local_hour < 12 else "afternoon" if 12 <= local_hour < 17 else "evening" if 17 <= local_hour < 21 else "night"
    greeting = (profile.get("greetings", {}).get(time_key) or greeting_defaults[time_key]).strip()
    display_name = profile.get("name", "").strip() or "Learner"
    with st.expander("⚙️ Personalize your Overview", expanded=False):
        st.caption("Customize your name, time-based greetings and daily focus goal. Your greeting preferences are saved with your progress.")
        with st.form("overview_personalization_form"):
            new_name = st.text_input("Display name", value=profile.get("name", ""), max_chars=40, placeholder="Your name or nickname")
            gc1, gc2 = st.columns(2)
            with gc1:
                g_morning = st.text_input("Morning greeting", value=profile["greetings"].get("morning", "Good morning"), max_chars=50)
                g_afternoon = st.text_input("Afternoon greeting", value=profile["greetings"].get("afternoon", "Good afternoon"), max_chars=50)
            with gc2:
                g_evening = st.text_input("Evening greeting", value=profile["greetings"].get("evening", "Good evening"), max_chars=50)
                g_night = st.text_input("Night greeting", value=profile["greetings"].get("night", "Good night"), max_chars=50)
            new_goal = st.number_input("Daily study goal (hours)", min_value=0.5, max_value=16.0, value=float(profile.get("goal_hours", 2.0)), step=0.5)
            saved_personalization = st.form_submit_button("Save Overview settings ✦", use_container_width=True)
        if saved_personalization:
            profile["name"] = new_name.strip()
            profile["greetings"] = {
                "morning": g_morning.strip() or "Good morning",
                "afternoon": g_afternoon.strip() or "Good afternoon",
                "evening": g_evening.strip() or "Good evening",
                "night": g_night.strip() or "Good night"
            }
            profile["goal_hours"] = float(new_goal)
            d["profile"] = profile
            save()
            st.success("Your Overview preferences have been saved.")
            st.rerun()
    gx, gy = st.columns([1.6, 1])
    with gy:
        st.markdown(f'<div class="greeting"><div class="eyebrow">✦ YOUR DAILY CHECK-IN</div><h2 style="margin:.35rem 0">{html.escape(greeting)}, {html.escape(display_name)}!</h2><div style="color:#c2d7ff">✨ Ready to make today count?</div></div>', unsafe_allow_html=True)
    today_hours = float(d.get("hours", {}).get(today, 0) or 0)
    goal_hours = float(profile.get("goal_hours", 2.0) or 2.0)
    goal_pct = min(1.0, today_hours / max(0.5, goal_hours))
    a,b,c,e = st.columns(4)
    a.metric("SYLLABUS XP", f"{done}/{len(all_topics)}", f"{pct}% complete")
    b.metric("FOCUS TIME", f"{hours_total:.1f} h", "logged on this device")
    c.metric("ACTIVE DAYS", active_days, f"{streak} day streak")
    e.metric("MEDALS", len(d["medals"]), f"{len(d['results'])} tests completed")
    st.progress(pct/100, text=f"Scholar level progress · {pct}%")
    st.progress(goal_pct, text=f"Today's focus goal · {today_hours:.1f}/{goal_hours:g} hours")
    left,right = st.columns([1.15,1],gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="kicker">✦ DAILY TRANSMISSION</div>',unsafe_allow_html=True)
            st.markdown("### “Great things are done by a series of small things brought together.”")
            st.caption("— Vincent van Gogh")
        with st.container(border=True):
            st.markdown('<div class="kicker">✦ ACTIVE QUESTS</div>',unsafe_allow_html=True)
            st.markdown("**Daily quest:** Log a study session")
            st.markdown("**Scholar quest:** Complete one syllabus topic")
            st.markdown("**Arena quest:** Attempt a Sets challenge")
            for s,ts in list(d.get("syllabus", {}).items())[:6]:
                n=sum(f"{s}:{t}" in d["completed"] for t in ts)
                st.caption(f"{s} · {n}/{len(ts)} cleared")
                st.progress(n/max(1,len(ts)))
    with right:
        with st.container(border=True):
            st.markdown('<div class="kicker">✦ YOUR AI COMPANION</div>',unsafe_allow_html=True)
            st.markdown("## 😄 Buddy is online")
            st.caption("Local model: llama3.2:3b · Ollama")
            for msg in d["messages"][-6:]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            q=st.chat_input("Ask a doubt or request an example…")
            if q:
                d["messages"].append({"role":"user","content":q}); save()
                with st.chat_message("user"): st.markdown(q)
                with st.chat_message("assistant"):
                    try:
                        with st.spinner("😄 Buddy is thinking…"):
                            r=requests.post(OLLAMA_URL,json={"model":MODEL,"messages":d["messages"][-12:],"stream":False},timeout=180)
                            r.raise_for_status(); answer=r.json()["message"]["content"]
                        st.markdown(answer); d["messages"].append({"role":"assistant","content":answer}); save()
                    except requests.RequestException:
                        st.error("Ollama couldn't be reached. Check that Ollama is running and llama3.2:3b is installed.")
        with st.container(border=True):
            st.markdown('<div class="kicker">✦ RECENT UNLOCKS</div>',unsafe_allow_html=True)
            st.markdown("  ".join(f"{emoji(m)} **{m}**" for m in d["medals"][-4:]) if d["medals"] else "🔒 Your first medal awaits in MCQ Arena.")

elif page == "Syllabus":
    hero("QUEST BOARD", "Your custom syllabus", "Add any subjects and as many chapters as you need. Your progress saves locally.")
    with st.container(border=True):
        st.markdown("### ＋ Create a subject")
        with st.form("add_subject_form", clear_on_submit=True):
            new_subject = st.text_input("Subject name", placeholder="e.g. Accountancy, Biology, Mathematics")
            add_subject = st.form_submit_button("Add subject ✦", use_container_width=True)
        if add_subject:
            name = new_subject.strip()
            if not name: st.warning("Enter a subject name first.")
            elif name in d["syllabus"]: st.warning("That subject already exists.")
            else: d["syllabus"][name] = []; save(); st.success(f"Added {name}!"); st.rerun()
    if not d.get("syllabus"):
        st.info("Your syllabus is empty. Add your first subject above.")
    for subject, chapters in list(d.get("syllabus", {}).items()):
        with st.container(border=True):
            done_count = sum(f"{subject}:{ch}" in d["completed"] for ch in chapters)
            c1,c2 = st.columns([4,1])
            c1.markdown(f"### 📘 {subject} · {done_count}/{len(chapters)}")
            with c2:
                if st.button("Delete subject", key="del_subject_"+subject):
                    d["syllabus"].pop(subject, None)
                    d["completed"] = [x for x in d["completed"] if not x.startswith(subject+":")]
                    save(); st.rerun()
            st.progress(done_count/max(1,len(chapters)), text=f"{round(done_count/max(1,len(chapters))*100)}% complete")
            with st.form("add_chapter_"+subject, clear_on_submit=True):
                chapter_name = st.text_input("Add a chapter", placeholder="Type chapter or unit name", key="chapter_input_"+subject)
                add_chapter = st.form_submit_button("＋ Add chapter")
            if add_chapter:
                ch = chapter_name.strip()
                if not ch: st.warning("Enter a chapter name first.")
                elif ch in chapters: st.warning("That chapter already exists in this subject.")
                else: d["syllabus"][subject].append(ch); save(); st.rerun()
            if chapters:
                for idx, chapter in enumerate(list(chapters)):
                    key = f"{subject}:{chapter}"
                    row1,row2,row3 = st.columns([5,1,1])
                    with row1:
                        checked = st.checkbox(chapter, value=key in d["completed"], key="chapter_done_"+key)
                    with row2:
                        if st.button("✎", key="rename_"+key, help="Rename chapter"):
                            st.session_state["rename_chapter"] = key
                    with row3:
                        if st.button("🗑", key="remove_"+key, help="Delete chapter"):
                            d["syllabus"][subject].remove(chapter); d["completed"] = [x for x in d["completed"] if x != key]; save(); st.rerun()
                    if checked and key not in d["completed"]:
                        d["completed"].append(key)
                        if "Scholar" not in d["medals"]: d["medals"].append("Scholar")
                        save(); st.rerun()
                    elif not checked and key in d["completed"]:
                        d["completed"].remove(key); save(); st.rerun()
                    if st.session_state.get("rename_chapter") == key:
                        with st.form("rename_form_"+key):
                            renamed = st.text_input("New chapter name", value=chapter)
                            do_rename = st.form_submit_button("Save chapter name")
                        if do_rename:
                            new_ch = renamed.strip()
                            if new_ch and new_ch not in chapters:
                                pos = d["syllabus"][subject].index(chapter); d["syllabus"][subject][pos] = new_ch
                                if key in d["completed"]: d["completed"].remove(key); d["completed"].append(f"{subject}:{new_ch}")
                                st.session_state.pop("rename_chapter", None); save(); st.rerun()
            else: st.caption("No chapters yet — add your first chapter above.")
    st.caption("Tip: the example subjects were migrated from your previous version. You can rename or delete them and create your own syllabus.")

elif page == "Study Journal":
    hero("BUILD YOUR STREAK","Study journal","Log your focused time and capture what clicked today.")
    st.caption("The live counter measures active time on this page, not guaranteed focused study time. It pauses while the tab is hidden and stores its count in this browser.")
    components.html(r"""
    <div style="font:600 14px system-ui;color:#dce9ff;padding:14px;border:1px solid #66e6f544;border-radius:14px;background:linear-gradient(135deg,#1a2b4c,#151a34)">
      <div style="color:#76eaff;font-size:11px;letter-spacing:.14em">TODAY'S ACTIVE WEBSITE TIME</div>
      <div id="sb-timer" style="font-size:26px;margin-top:5px">00:00:00</div>
      <div style="font-size:11px;color:#aab6d7;margin-top:4px">Saved in this browser · pauses when this tab is hidden</div>
    </div>
    <script>
    (() => {
      const key='studybuddy_active_seconds_'+new Date().toLocaleDateString('en-CA');
      let total=Number(localStorage.getItem(key)||0), last=Date.now();
      const node=document.getElementById('sb-timer');
      const paint=()=>{const h=Math.floor(total/3600),m=Math.floor(total%3600/60),s=Math.floor(total%60);node.textContent=[h,m,s].map(v=>String(v).padStart(2,'0')).join(':')};
      const tick=()=>{const now=Date.now();if(!document.hidden)total+=Math.min(5,Math.max(0,(now-last)/1000));last=now;localStorage.setItem(key,String(Math.floor(total)));paint()};
      document.addEventListener('visibilitychange',()=>{last=Date.now()});
      paint();setInterval(tick,1000);
    })();
    </script>
    """, height=105, scrolling=False)
    with st.container(border=True):
        hrs=st.number_input("Hours studied today",0.0,24.0,float(d["hours"].get(today,0)),step=.5)
        note=st.text_area("Today's learning note",d["journal"].get(today,""),placeholder="What did you learn? What needs another look?")
        if st.button("Save study session",use_container_width=True):
            d["hours"][today]=hrs; d["journal"][today]=note
            if hrs>0 and streak>=6 and "Streak Keeper" not in d["medals"]: d["medals"].append("Streak Keeper")
            save(); st.success("Session saved!")
    with st.container(border=True):
        st.markdown("### Focus history")
        if d["hours"]:
            st.bar_chart({k:float(v) for k,v in sorted(d["hours"].items())})
            st.dataframe([{"Date":k,"Hours":v,"Note":d["journal"].get(k,"")} for k,v in sorted(d["hours"].items(),reverse=True)],use_container_width=True,hide_index=True)
        else: st.info("Your first session will start the chart.")

elif page == "MCQ Arena":
    hero("TRAIN YOUR BRAIN", "MCQ Arena", "Your local AI builds a fresh quiz from the exact subject and chapter you select.")
    syllabus = d.get("syllabus", {})
    if not syllabus or not any(chapters for chapters in syllabus.values()):
        st.warning("Add a subject and at least one chapter in Your Custom Syllabus before generating a quiz.")
    else:
        available_subjects = [name for name, chapters in syllabus.items() if chapters]
        selected_subject = st.selectbox("1 · Choose subject", available_subjects, key="mcq_subject")
        available_chapters = syllabus.get(selected_subject, [])
        selected_chapter = st.selectbox("2 · Choose chapter", available_chapters, key="mcq_chapter")
        chapter_notes = st.text_area(
            "Chapter notes / textbook content (recommended)",
            key="mcq_notes",
            placeholder="Paste definitions, examples, formulas or textbook notes for this chapter. The AI will use these to keep questions accurate.",
            help="The local model may not know your exact textbook. Adding chapter content makes questions more reliable and reduces topic mixing."
        )
        question_count = st.slider("Number of MCQs", min_value=5, max_value=20, value=10, step=5, key="mcq_count")
        st.caption(f"Selected scope: **{selected_subject} → {selected_chapter}**. Questions from other chapters must not appear.")
        if st.button("✦ Generate chapter-specific MCQs", use_container_width=True, type="primary"):
            try:
                with st.spinner(f"Local AI is creating questions for {selected_chapter}…"):
                    generated = generate_chapter_mcqs(selected_subject, selected_chapter, chapter_notes, question_count)
                st.session_state["chapter_quiz"] = generated
                st.session_state["chapter_quiz_subject"] = selected_subject
                st.session_state["chapter_quiz_chapter"] = selected_chapter
                st.session_state["chapter_quiz_submitted"] = False
                st.session_state["chapter_quiz_saved"] = False
                st.session_state.pop("chapter_quiz_answers", None)
                st.rerun()
            except requests.exceptions.ConnectionError:
                st.error("Couldn't reach Ollama. Start Ollama and make sure the local model 'llama3.2:3b' is installed.")
            except requests.exceptions.Timeout:
                st.error("The local AI took too long to respond. Try fewer questions or shorter chapter notes.")
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                st.error(f"MCQ generation failed: {exc}")

    quiz = st.session_state.get("chapter_quiz", [])
    quiz_subject = st.session_state.get("chapter_quiz_subject", "")
    quiz_chapter = st.session_state.get("chapter_quiz_chapter", "")
    if quiz:
        st.divider()
        st.markdown(f"### {html.escape(quiz_subject)} · {html.escape(quiz_chapter)}")
        st.markdown(f'<span class="pill">LOCAL AI</span><span class="pill">{len(quiz)} QUESTIONS</span><span class="pill">CHAPTER-LOCKED</span>', unsafe_allow_html=True)
        if len(quiz) < st.session_state.get("mcq_count", 10):
            st.info(f"The local AI could support only {len(quiz)} reliable question(s) from this chapter, so unrelated questions were not added.")
        if st.session_state.get("chapter_quiz_submitted", False):
            answers = st.session_state.get("chapter_quiz_answers", {})
            score = sum(answers.get(i) == q["answer"] for i, q in enumerate(quiz))
            mistakes = len(quiz) - score
            medal = medal_for(mistakes) if len(quiz) == 10 else ("Gold" if mistakes == 0 else "Silver" if mistakes == 1 else "Bronze" if mistakes <= 3 else None)
            st.metric("FINAL SCORE", f"{score}/{len(quiz)}", f"{mistakes} mistakes")
            if medal:
                st.markdown(f'<div class="medal"><div class="icon">{emoji(medal)}</div><h2>{medal.upper()} MEDAL</h2><p>Achievement added to your cabinet.</p></div>', unsafe_allow_html=True)
                if medal not in d["medals"]: d["medals"].append(medal)
            for i, q in enumerate(quiz):
                st.markdown(f"**Q{i+1}. {q['question']}**")
                picked = answers.get(i)
                if picked == q["answer"]:
                    st.success("Correct · " + q["options"][q["answer"]])
                else:
                    your_answer = q["options"][picked] if isinstance(picked, int) and 0 <= picked < 4 else "Not answered"
                    st.error("Your answer: " + your_answer + " · Correct: " + q["options"][q["answer"]])
                st.caption("💡 " + q["explanation"])
            if not st.session_state.get("chapter_quiz_saved", False):
                d["results"].append({"date": today, "subject": quiz_subject, "topic": quiz_chapter, "score": score, "total": len(quiz), "medal": medal})
                save(); st.session_state["chapter_quiz_saved"] = True
            if st.button("Generate another quiz ↻", use_container_width=True):
                st.session_state["chapter_quiz_submitted"] = False
                st.session_state["chapter_quiz_saved"] = False
                st.session_state.pop("chapter_quiz_answers", None)
                st.rerun()
        else:
            selected = {}
            with st.form("chapter_mcq_form"):
                for i, q in enumerate(quiz):
                    st.markdown(f"**{i+1:02d} / {len(quiz)} · {q['question']}**")
                    selected[i] = st.radio("Pick an answer", q["options"], index=None, key=f"chapter_answer_{i}", label_visibility="collapsed")
                if st.form_submit_button("Lock answers & reveal score ✦", use_container_width=True):
                    st.session_state["chapter_quiz_answers"] = {i: q["options"].index(selected[i]) for i, q in enumerate(quiz) if selected[i] in q["options"]}
                    st.session_state["chapter_quiz_submitted"] = True
                    st.session_state["chapter_quiz_saved"] = False
                    st.rerun()
elif page == "Medal Cabinet":
    hero("ACHIEVEMENTS & RANK", "The Medal Vault", "100+ collectibles. Earn them through real study progress, focus time and MCQ results.")
    golds=sum(r.get("medal")=="Gold" for r in d["results"])
    if golds>=5 and "Perfectionist" not in d["medals"]: d["medals"].append("Perfectionist"); save()
    # Auto-award milestone medals from locally recorded activity.
    total_hours = int(hours_total)
    total_tests = len(d["results"])
    perfect_tests = sum(r.get("score",0)==r.get("total",10) for r in d["results"])
    earned = set(d["medals"])
    for m in MEDAL_DEFS:
        name=m["name"]
        if name.startswith("Day ") and len(d.get("visit_dates",[])) >= int(name.split()[1]): earned.add(name)
        elif name.startswith("Focus Forge ") and total_hours >= int(name.split()[-1]): earned.add(name)
        elif name.startswith("Chapter Conqueror ") and done >= int(name.split()[-1]): earned.add(name)
        elif name.startswith("Arena Victor ") and total_tests >= int(name.split()[-1]): earned.add(name)
        elif name.startswith("Precision Star ") and perfect_tests >= int(name.split()[-1]): earned.add(name)
        elif name.startswith("Scholar Explorer ") and len(d.get("syllabus",{})) >= int(name.split()[-1]): earned.add(name)
    d["medals"] = list(earned); save()
    st.caption(f"{len(d['medals'])} medals earned · {len(MEDAL_DEFS)} collectibles · {golds}/5 perfect tests")
    query=st.text_input("Search medals", placeholder="Search achievements…")
    categories=["All"]+sorted({m["category"] for m in MEDAL_DEFS})
    category=st.selectbox("Category",categories)
    rarities=["All","Common","Uncommon","Rare","Epic","Legendary","Mythic"]
    rarity=st.selectbox("Rarity",rarities)
    visible=[m for m in MEDAL_DEFS if (category=="All" or m["category"]==category) and (rarity=="All" or m["rarity"]==rarity) and query.lower() in (m["name"]+m["desc"]+m["category"]).lower()]
    st.markdown(f"**Showing {len(visible)} / {len(MEDAL_DEFS)} achievements**")
    rarity_color={"Common":"#b7c4df","Uncommon":"#65e6c3","Rare":"#72b9ff","Epic":"#c3a0ff","Legendary":"#ffd778","Mythic":"#ff8acb"}
    cols=st.columns(3)
    for i,m in enumerate(visible):
        unlocked=m["name"] in d["medals"]
        with cols[i%3]:
            st.markdown(f'<div class="medal" style="border-color:{rarity_color[m["rarity"]]}55"><div class="icon">{emoji(m["name"]) if unlocked else "🔒"}</div><h3 style="margin:.5rem 0">{m["name"]}</h3><div style="color:{rarity_color[m["rarity"]]};font-weight:700;font-size:.75rem;letter-spacing:.12em">{m["rarity"].upper()}</div><p>{"UNLOCKED ✓" if unlocked else "LOCKED"}</p></div>',unsafe_allow_html=True)
            st.caption(m["desc"])
            if not unlocked:
                if m["name"].startswith("Chapter Conqueror "): current=done; target=int(m["name"].split()[-1])
                elif m["name"].startswith("Focus Forge "): current=total_hours; target=int(m["name"].split()[-1])
                elif m["name"].startswith("Arena Victor "): current=total_tests; target=int(m["name"].split()[-1])
                elif m["name"].startswith("Precision Star "): current=perfect_tests; target=int(m["name"].split()[-1])
                elif m["name"].startswith("Day "): current=len(d.get("visit_dates",[])); target=int(m["name"].split()[1])
                elif m["name"].startswith("Scholar Explorer "): current=len(d.get("syllabus",{})); target=int(m["name"].split()[-1])
                else: current=0; target=1
                st.progress(min(1,current/max(1,target)),text=f"Progress: {min(current,target)}/{target}")
    st.markdown("### Test history")
    if d["results"]: st.dataframe(d["results"][::-1],use_container_width=True,hide_index=True)
    else: st.caption("No tests completed yet.")
    st.info("Imperial Laurel is reserved for the top 10% of a real shared leaderboard. This local-only version cannot truthfully award or revoke it without online accounts and shared rankings.")

elif page == "Scholar Network":
    hero("YOUR SCHOLAR IDENTITY", "Scholar Network", "Set a distinct name and username for your StudyBuddy identity.")
    p=d["profile"]
    people=d["network"]["people"]
    with st.container(border=True):
        st.markdown("### ✦ Your profile")
        name=st.text_input("Display name (must be unique)",p.get("name",""),key="profile_display_name")
        username=st.text_input("Username (must be unique)",p.get("username",""),placeholder="e.g. niki.study",key="profile_username")
        share=st.toggle("Share subject strengths and help goals",p.get("share",False),key="profile_share")
        strong=st.multiselect("Subjects I can help with",sorted(set(list(d.get("syllabus", {}).keys())+["English","Economics","Biology"])),p.get("strong",[]),key="profile_strong")
        help_with=st.multiselect("Subjects I want help with",sorted(set(list(d.get("syllabus", {}).keys())+["English","Economics","Biology"])),p.get("help",[]),key="profile_help")
        if st.button("Save profile ✦",use_container_width=True,key="save_profile_social"):
            clean_name=name.strip(); clean_username=username.strip().lstrip("@").lower()
            name_taken=any(x.get("name","").casefold()==clean_name.casefold() for x in people)
            user_taken=any(x.get("username","").casefold()==clean_username.casefold() for x in people)
            if not clean_name or not clean_username:
                st.warning("Add both a display name and a username.")
            elif len(clean_username)<3 or any(ch.isspace() for ch in clean_username):
                st.warning("Username must be at least 3 characters and contain no spaces.")
            elif name_taken or user_taken:
                st.error("That display name or username is already taken. Choose a unique one.")
            else:
                d["profile"].update({"name":clean_name,"username":clean_username,"share":share,"strong":strong,"help":help_with})
                save(); st.success("Profile saved on this computer."); st.rerun()
    with st.container(border=True):
        st.markdown(f"## 🎓 {p.get('name') or 'Anonymous Scholar'}")
        st.caption("@"+(p.get("username") or "username-not-set"))
        if p.get("share"):
            st.markdown("**Can help with:** "+(", ".join(p.get("strong",[])) or "Not specified"))
            st.markdown("**Wants help with:** "+(", ".join(p.get("help",[])) or "Not specified"))
        else: st.caption("Your subject details stay private until you opt in.")
    st.info("Scholar Network still includes local demo profiles. Global Lobby is the shared cross-device room when Supabase is configured.")

elif page == "Global Lobby":
    hero("ONE WORLDWIDE STUDY ROOM", "Global Lobby", "Meet learners in one shared room. Messages show the sender's nickname.")
    auth = st.session_state.get(_AUTH_KEY, {})
    token = auth.get("access_token")
    profile = d.setdefault("profile", {})
    nickname = st.text_input("Lobby nickname", value=profile.get("name", "").strip() or profile.get("username", "").strip(), max_chars=32, key="lobby_nickname")
    st.caption("Be kind. Never post passwords, phone numbers, addresses or other private information.")
    if not SUPABASE_READY:
        st.warning("The shared Global Lobby needs a Supabase project. Configure SUPABASE_URL and SUPABASE_ANON_KEY, then run SETUP_GLOBAL_LOBBY.sql included with this build.")
    elif not token:
        st.info("Log in to join the shared Global Lobby.")
    else:
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/global_messages",
                params={"select":"id,nickname,content,created_at","order":"created_at.desc","limit":"80"},
                headers=_sb_headers(token), timeout=15)
            r.raise_for_status()
            messages = list(reversed(r.json()))
            st.markdown("### 💬 Lobby chat")
            if not messages: st.caption("You're first — say hello!")
            for msg in messages:
                with st.container(border=True):
                    st.caption(html.escape(str(msg.get("nickname") or "Learner")) + " · " + str(msg.get("created_at",""))[:16].replace("T"," "))
                    st.markdown(html.escape(str(msg.get("content",""))))
            with st.form("global_lobby_send", clear_on_submit=True):
                message = st.text_area("Message everyone", max_chars=500, placeholder="Share a study tip, ask a question, or say hi…")
                send_message = st.form_submit_button("Send to Global Lobby ↗", use_container_width=True)
            if send_message:
                clean_name, clean_message = nickname.strip()[:32], message.strip()
                if not clean_name or not clean_message:
                    st.warning("Add a nickname and message first.")
                else:
                    post = requests.post(f"{SUPABASE_URL}/rest/v1/global_messages",
                        json={"nickname":clean_name,"content":clean_message,"user_id":auth.get("user", {}).get("id")},
                        headers=_sb_headers(token,"return=minimal"), timeout=15)
                    if post.status_code >= 400: st.error("Message wasn't sent. Check the lobby table permissions.")
                    else: st.rerun()
            if st.button("Refresh messages ↻"): st.rerun()
        except Exception as exc:
            st.error(f"Couldn't connect to the Global Lobby: {exc}")
    st.caption("Messages are visible to other signed-in learners when the shared backend is configured.")

elif page == "Talk to Your Mates":
    hero("YOUR STUDY CREW", "Talk to Your Mates", "Friend requests first. Private chats unlock only after a request is accepted.")
    net=d["network"]; current=d["profile"]
    if not current.get("username"):
        st.warning("Set your username in Scholar Network first so your study identity is ready.")
    people_by_user={x.get("username"):x for x in net["people"]}
    incoming=net.get("incoming",[])
    sent=net.get("sent",[])
    friends=net.get("friends",[])
    left,right=st.columns(2,gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### ✉️ Incoming requests")
            if not incoming: st.caption("No pending requests right now.")
            for req in list(incoming):
                uname=req.get("username",""); person=people_by_user.get(uname,{"name":uname,"emoji":"🌟"})
                st.markdown(f"**{person.get('emoji','🌟')} {html.escape(person.get('name',uname))}** · @{html.escape(uname)}")
                st.caption(req.get("message","Wants to study together."))
                a1,a2=st.columns(2)
                with a1:
                    if st.button("Accept ✓",key="accept_"+uname,use_container_width=True):
                        net["incoming"]=[r for r in net["incoming"] if r.get("username")!=uname]
                        if uname not in net["friends"]: net["friends"].append(uname)
                        if uname in net["sent"]: net["sent"].remove(uname)
                        save(); st.rerun()
                with a2:
                    if st.button("Decline",key="decline_"+uname,use_container_width=True):
                        net["incoming"]=[r for r in net["incoming"] if r.get("username")!=uname]; save(); st.rerun()
    with right:
        with st.container(border=True):
            st.markdown("### 📨 Requests you sent")
            if not sent: st.caption("You haven't sent any requests yet. Explore Find Your Mates.")
            for uname in list(sent):
                person=people_by_user.get(uname,{"name":uname,"emoji":"🌟"})
                st.markdown(f"{person.get('emoji','🌟')} **{html.escape(person.get('name',uname))}** · @{html.escape(uname)}")
                st.caption("Waiting for acceptance")
                if st.button("Demo: accept this request",key="demo_accept_"+uname,help="Local prototype only: simulate the other demo profile accepting.",use_container_width=True):
                    net["sent"]=[x for x in net["sent"] if x!=uname]
                    if uname not in net["friends"]: net["friends"].append(uname)
                    save(); st.success("Demo request accepted. Chat is now unlocked."); st.rerun()
    st.markdown("### 💬 Your friends")
    if not friends:
        st.info("No accepted friends yet. Send a request from Find Your Mates, then use the demo acceptance control to preview the chat flow.")
    for uname in list(friends):
        person=people_by_user.get(uname,{"name":uname,"emoji":"🌟"})
        with st.container(border=True):
            st.markdown(f"### {person.get('emoji','🌟')} {html.escape(person.get('name',uname))}  ·  <span style='color:#79e9f6'>ONLINE DEMO</span>",unsafe_allow_html=True)
            st.caption("@"+html.escape(uname)+" · "+", ".join(person.get("subjects",[])))
            chat_key=uname
            messages=net.setdefault("messages",{}).setdefault(chat_key,[])
            for msg in messages[-12:]:
                with st.chat_message(msg.get("role","user")):
                    st.markdown(msg.get("content",""))
            with st.form("chat_form_"+uname,clear_on_submit=True):
                msg_text=st.text_input("Message",placeholder=f"Message {person.get('name',uname)}…",key="chat_input_"+uname)
                send=st.form_submit_button("Send message ↗",use_container_width=True)
            if send and msg_text.strip():
                messages.append({"role":"user","content":msg_text.strip(),"at":datetime.now().isoformat(timespec="minutes")})
                # Demo reply makes the prototype feel interactive; clearly labelled as simulated.
                messages.append({"role":"assistant","content":f"Hey! 👋 I’m the local demo profile for {person.get('name',uname)}. Your message is saved in this prototype. With a shared online backend, this chat can connect to a real student.","at":datetime.now().isoformat(timespec="minutes"),"demo":True})
                save(); st.rerun()
    with st.expander("🧪 Test incoming requests (local demo)"):
        st.caption("Creates a clearly labelled sample request so you can test Accept and Decline without needing a second device.")
        options=[x for x in net["people"] if x.get("username") not in friends and x.get("username") not in {r.get("username") for r in net["incoming"]} and x.get("username") not in sent and x.get("username")!=current.get("username")]
        if options:
            request_person=st.selectbox("Choose demo person",options,format_func=lambda x:f"{x.get('name')} (@{x.get('username')})",key="demo_incoming_choice")
            if st.button("Create sample request",use_container_width=True):
                net["incoming"].append({"username":request_person["username"],"message":"This is a simulated request from a local demo profile."}); save(); st.rerun()
        else: st.caption("No available demo profiles to use for a sample request.")

save()
st.markdown("---")
st.markdown("""
<div style="text-align:center;padding:8px 6px 4px;color:#94a6c9;font-size:.76rem;line-height:1.7">
  <div style="letter-spacing:.12em;font-weight:700;color:#c8d5f4">STUDYBUDDY AI · QUEST MODE</div>
  <div>Keep learning. Keep growing. ✦</div>
  <a href="https://www.instagram.com/uzumaki_niki_da/" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:5px;color:#b9a8ff;text-decoration:none;font-size:.75rem">◎ Follow @uzumaki_niki_da on Instagram</a>
  <div style="font-size:.7rem;color:#8798bb">DM for help regarding the web app</div>
</div>
""", unsafe_allow_html=True)
