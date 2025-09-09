import streamlit as st
import base64
import requests
import json
import io
from typing import List, Dict

# ========= App meta =========
st.set_page_config(page_title="Generator kolorowanek ", page_icon="🎨", layout="wide")
st.title("🎨 Generator kolorowanek - napisz motyw i generuj kolorowankę")

sbar = st.sidebar
sbar.title("⚙️ Ustawienia kolorowanek")

# ========= Config =========
with sbar.expander("Podaj klucz do OPENAI API"):
    BASE_URL = st.session_state.get("BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY = st.text_input("🔑 Podaj swój OPENAI_API_KEY aby wygenerować kolorowankę", type="password")
    TEXT_MODEL = st.text_input("🧠 (LLM) model do pomysłów", value=st.session_state.get("TEXT_MODEL", "gpt-4o-mini"))

with sbar.expander("Zaawansowane (opcjonalnie)", expanded=False):
    OPENAI_ORG_ID = st.text_input("🏢 OpenAI Organization ID (org_…)", value=st.session_state.get("OPENAI_ORG_ID", ""))
    OPENAI_PROJECT_ID = st.text_input("📦 OpenAI Project ID (proj_…)", value=st.session_state.get("OPENAI_PROJECT_ID", ""))

with sbar.expander("⚙️ Debug / Info"):
    st.code(json.dumps({
        "BASE_URL": BASE_URL,
        "TEXT_MODEL": TEXT_MODEL,
        "has_api_key": bool(OPENAI_API_KEY),
        "org_id": OPENAI_ORG_ID or None,
        "project_id": OPENAI_PROJECT_ID or None,
    }, ensure_ascii=False, indent=2))


# ========= Helpers =========
def _headers() -> Dict[str, str]:
    h = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    if OPENAI_ORG_ID.strip():
        h["OpenAI-Organization"] = OPENAI_ORG_ID.strip()
    if OPENAI_PROJECT_ID.strip():
        h["OpenAI-Project"] = OPENAI_PROJECT_ID.strip()
    return h

TAIL = ", black-and-white coloring book page, clean bold outlines, no shading, white background, centered composition, high contrast lines, vector-line look"

def normalize_coloring_prompt(p: str) -> str:
    return (p or "").strip() + TAIL

def llm_generate_ideas(theme: str) -> List[Dict[str, str]]:
    """Zwraca listę obiektów {title, prompt}. Odporne na code-fence i różne klucze."""
    url = BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": "Return strict JSON only, no markdown. Schema: {\"items\":[{\"title\":\"string\",\"prompt\":\"string\"}]}."},
            {"role": "user", "content": (
                "Zaprojektuj 12 pomysłów na kolorowanki dla dzieci na temat: '" + theme + "'. "
                "Każdy pomysł zamień w krótki PROMPT. Wymogi: czarno-białe, czyste kontury, brak cieniowania, białe tło, "
                "prosty styl, linie 2–5 px, 1024×1024, centralny kadr, brak tekstu/napisów. Zwróć WYŁĄCZNIE JSON w schemacie "
                "{\"items\":[{\"title\":\"string\",\"prompt\":\"string\"}]}"
            )}
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"}
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=60)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()

    # spróbuj bezpośrednio
    try:
        obj = json.loads(content)
    except Exception:
        # usuń ewentualne ```json … ```
        content = content.strip("` ")
        obj = json.loads(content)

    items = None
    if isinstance(obj, dict):
        for k in ("items", "ideas", "coloring_pages", "data", "prompts"):
            if k in obj and isinstance(obj[k], list):
                items = obj[k]
                break
    if items is None and isinstance(obj, list):
        items = obj
    if not items:
        return []

    out = []
    for it in items:
        if isinstance(it, dict):
            title = it.get("title") or it.get("name") or it.get("label") or "Pomysł"
            prompt = it.get("prompt") or it.get("text") or it.get("description") or ""
            if prompt.strip():
                out.append({"title": title, "prompt": prompt})
    return out


def gen_image_openai(prompt: str, size_px: int = 1024, quality: str = "high") -> bytes:
    if not OPENAI_API_KEY:
        raise RuntimeError("Brak OPENAI_API_KEY")
    url = BASE_URL.rstrip("/") + "/images/generations"
    payload = {
        "model": "gpt-image-1",
        "prompt": normalize_coloring_prompt(prompt),
        "size": f"{size_px}x{size_px}",
        "n": 1,
        "quality": quality,
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=120)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text[:1000]}
        raise RuntimeError(f"Błąd API: {json.dumps(err, ensure_ascii=False)}")
    b64 = r.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)

# ========= State =========
if "ideas" not in st.session_state:
    st.session_state["ideas"] = []
if "generated_images" not in st.session_state:
    st.session_state["generated_images"] = []

st.caption("Sposób działania aplikacji: 1. wybierz temat → powstaje lista promptów → wybierasz jedne pomysł → ustalasz liczbę wariantów → aplikacja generuje obrazki → pobieranie kolorowanek")

# ========= UI – v1: temat → lista promptów =========
st.header("Wpisz temat i wygeneruj propozycje promptów")
colA, colB = st.columns([2,1])
with colA:
    theme = st.text_input("Wpisz temat kolorowanek (np. 'smoki i zamki', 'las deszczowy', 'kosmos dla przedszkolaków'):")
with colB:
    n_ideas = st.slider("Ile pomysłów wygenerować (max 6)", 6, 4, 2)

if st.button("🔮 Generuj pomysły na kolorowanki", type="primary"):
    if not theme.strip():
        st.warning("Podaj temat.")
    else:
        try:
            ideas = llm_generate_ideas(theme)
            st.session_state["ideas"] = ideas[:n_ideas]
            st.success(f"Gotowe: {len(st.session_state['ideas'])} propozycji.")
        except Exception as e:
            st.error(str(e))

ideas = st.session_state.get("ideas", [])
if ideas:
    st.subheader("Pomysły i prompty (edytowalne) – wybierz, którego użyć")
    titles = [f"{i+1}. {it['title']}" for i, it in enumerate(ideas)]
    choice_idx = st.selectbox("Który prompt wykorzystać?", options=list(range(len(titles))), format_func=lambda i: titles[i])

    # Edycja wybranego
    with st.expander("✏️ Edytuj wybrany prompt"):
        sel = ideas[choice_idx]
        new_title = st.text_input("Tytuł", value=sel["title"], key="sel_title")
        new_prompt = st.text_area("Prompt", value=sel["prompt"], key="sel_prompt", height=120)
        # zapisz zmiany do state
        sel["title"], sel["prompt"] = new_title, new_prompt

# ========= UI – v2: wybór ilości rysunków z wybranego promptu =========
st.header("Wybierz liczbę rysunków do wygenerowania z wybranego promptu")
col1, col2, col3 = st.columns([1,1,1])
with col1:
    size_label = st.selectbox("Rozmiar kolorowanki", [512, 1024], index=1)
with col2:
    quality = st.selectbox("Jakość kolorowanki", ["low", "medium", "high", "auto"], index=2)
with col3:
    n_variants = st.number_input("Ile wariantów kolorowanki narysować (min 1 - max 6)?", min_value=1, max_value=6, value=1)

# ========= UI – v3: generacja =========
st.header("Generuj i pobieraj kolorowanki")
if st.button("🖨️ Generuj teraz kolorowanki", type="primary"):
    if not ideas:
        st.warning("Najpierw wygeneruj i wybierz prompt powyżej.")
    else:
        base_prompt = st.session_state["ideas"][choice_idx]["prompt"]
        with st.spinner(f"Teraz generuję dla ciebie {n_variants} obrazków i mam nadzieję że ci się spodobają:)"):
            imgs = []
            for i in range(int(n_variants)):
                # lekkie modyfikacje, żeby wymusić różnorodność wariantów
                prompt_variant = base_prompt + f", variant {i+1}"
                try:
                    png = gen_image_openai(prompt_variant, size_px=int(size_label), quality=quality)
                    imgs.append(png)
                except Exception as e:
                    st.error(str(e))
            if imgs:
                st.session_state["generated_images"] = imgs
                st.success("Gotowe.")

# Podgląd + indywidualne pobieranie + ZIP całości
pngs = st.session_state.get("generated_images", [])
if pngs:
    st.subheader("Podgląd i pobieranie kolorowanek")
    cols = st.columns(3)
    for i, png in enumerate(pngs, start=1):
        with cols[(i-1) % 3]:
            st.image(png, caption=f"Wariant #{i}", use_container_width=True)
            st.download_button(
                label=f"⬇️ Pobierz kolorowankę nr {i}",
                data=png,
                file_name=f"coloring_variant_{i:02d}.png",
                mime="image/png",
                key=f"dl_png_{i}"
            )

    # opcjonalnie: zbiorczy ZIP
    import zipfile
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, png in enumerate(pngs, start=1):
            zf.writestr(f"coloring_variant_{i:02d}.png", png)
    st.download_button(
        "⬇️ Pobierz wszystkie kolorowanki jako ZIP",
        data=zip_buf.getvalue(),
        file_name="coloring_variants.zip",
        mime="application/zip",
        use_container_width=True,
        key="dl_zip_all",
    )
