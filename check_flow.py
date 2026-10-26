"""Sanity check: core imports and helpers load (no Ollama or network). Run: python check_flow.py"""
import sys
sys.path.insert(0, ".")

def main():
    errors = []
    # Config
    try:
        from config import PHASE_MODELS, OLLAMA_FALLBACK_MODEL
        assert "gemma" in OLLAMA_FALLBACK_MODEL.lower(), "Expected Gemma in fallback model"
        assert all("gemma" in str(v).lower() for v in PHASE_MODELS.values()), "Expected Gemma in PHASE_MODELS"
        print("[OK] config (Gemma models)")
    except Exception as e:
        errors.append(("config", e))

    # LLM client
    try:
        from llm_client import get_model, generate_json
        m = get_model("phase_1")
        assert m and "gemma" in m.lower()
        print("[OK] llm_client.get_model")
    except Exception as e:
        errors.append(("llm_client", e))

    # Schemas
    try:
        from schemas import make_id, make_row_id
        assert make_id("RISK", 1) == "RISK-001"
        assert "UI_" in make_row_id("UI", 1)
        print("[OK] schemas")
    except Exception as e:
        errors.append(("schemas", e))

    # Ingestion
    try:
        from ingestion import extract_text, chunk_text
        t = chunk_text("Hello world. " * 100, source_name="test.txt")
        assert len(t) >= 1 and t[0].get("text") and t[0].get("source_name") == "test.txt"
        print("[OK] ingestion.chunk_text")
    except Exception as e:
        errors.append(("ingestion", e))

    # Prompts
    try:
        from prompts.phase_1 import build_phase_1_prompt
        from prompts.phase_2 import build_phase_2_prompt
        from prompts.phase_3 import build_phase_3_prompt
        from prompts.feedback import build_phase_1_feedback_prompt
        p1 = build_phase_1_prompt("Sample regulation text.", source_filename="reg.pdf")
        assert "COSO" in p1 and "Sample regulation" in p1
        print("[OK] prompts (phase_1, phase_2, phase_3, feedback)")
    except Exception as e:
        errors.append(("prompts", e))

    # Phases (imports only; no LLM calls)
    try:
        from phases.phase_1 import _merge_key, _deduplicate_risks, _quote_key, _deduplicate_by_quote
        from phases.phase_2 import _normalise_choice
        from phases import phase_3

        assert callable(phase_3.run_phase_3)
        key = _merge_key("Failure to comply may result in fines.")
        assert "comply" in key.lower()
        print("[OK] phases (phase_1, phase_2, phase_3)")
    except Exception as e:
        errors.append(("phases", e))

    # UI modules (import only)
    try:
        from ui.session_manager import init_sessions, get_active_id, get_session_list
        from ui.exporters import build_excel, build_pdf
        from ui.styles import phase_banner, html_table
        print("[OK] ui (session_manager, exporters, styles)")
    except Exception as e:
        errors.append(("ui", e))

    if errors:
        for name, e in errors:
            print(f"[FAIL] {name}: {e}")
        return 1
    print("\nAll checks passed.")
    return 0

if __name__ == "__main__":
    exit(main())
