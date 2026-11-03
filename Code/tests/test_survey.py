"""The investor survey: de-identified loading and the figures built from it."""
import pandas as pd

from src.site_export.survey import build_survey
from src.survey.load import load


def test_loader_drops_personal_columns_and_splits_multiple_picks(tmp_path):
    path = tmp_path / "survey.csv"
    pd.DataFrame({
        "Timestamp": ["2026/10/01 10:00"],
        "Q2. Have you ever started a SIP (Systematic Investment Plan)?": ["Yes"],
        "Q7. What influenced you to start SIP investing?": ["Family;Friends"],
        "Q22. What do you wish your investment app explained better?": ["Call me on 9876543210 about returns"],
        "Q28. How likely are you to continue your SIP over the next 12 months?": [5.0],
        "Q31. Would you be willing to participate in a 15-minute follow-up discussion?": ["Yes"],
        "Q32. Name (Optional)": ["Asha Rao"],
        "Q33. Email Address (Optional)": ["asha@example.com"],
    }).to_csv(path, index=False)
    responses, questions, report = load(path)
    row = responses[0]
    assert set(row) == {"id", "q2", "q7", "q22", "q28"}
    assert row["q7"] == ["Family", "Friends"] and row["q28"] == 5
    assert "9876543210" not in row["q22"] and report["personal_data_replaced_in_free_text"]["PHONE"] == 1
    assert "Asha" not in str(responses) and "@" not in str(responses)
    assert set(questions) == {"q2", "q7", "q22", "q28"} and report["sip_investors"] == 1


def response(i, check="Weekly", considered="No", reasons=(), future=(), active="Yes", likely=5, q29=""):
    return {"id": f"s{i}", "q2": "Yes", "q1": "26-30", "q4": "Salaried Employee", "q13": "1-2 Years",
            "q15": check, "q16": "Return %", "q17": considered, "q18": list(reasons), "q19": ["Google Search"],
            "q23": [], "q25": active, "q27": list(future), "q28": likely, "q29": q29}


ENGINE = {"problem_posts": 100, "instalments": 50, "returns_confusion": 20, "losses": 2, "cash": 3,
          "controls": 12, "help": 40}


def test_patterns_and_reasons_follow_the_ui_spec_definitions():
    rows = [response(1, "Weekly", "Yes", ["Poor Returns"], ["Poor Returns"]),
            response(2, "Daily", "Yes", ["Job Loss"], ["Job Loss"], active="No", likely=4),
            response(3, "Monthly", "Yes", ["Market Fall", "Financial Emergency"], ["Financial Emergency"],
                     q29="I have paused/reduced SIPs due to uncertainty."),
            response(4, "Rarely"),
            {"id": "s5", "q2": "No"}]
    s = build_survey(rows, ENGINE)
    assert s["sample"]["n"] == 4 and s["sample"]["responses"] == 5
    assert [(r["key"], r["n"]) for r in s["dropoffs"]["why_considered"]] == [("market", 1), ("cash", 1), ("both", 1)]
    assert s["dropoffs"]["future_cash"] == 2 and s["dropoffs"]["future_market"] == 1 and s["dropoffs"]["active"] == 3
    watcher, quiet, squeezed = s["segments"]["patterns"]
    assert watcher["n"] == 2 and watcher["detail"] == "2 have considered stopping"
    assert quiet["n"] == 2 and "1 say they paused or reduced" in quiet["detail"]
    assert squeezed["n"] == 2 and squeezed["detail"] == "1 still active; 2 rate continuing 4 or 5 of 5"
    assert s["journey"]["weekly_or_more"] == 2


def test_engine_vs_survey_readings():
    rows = [response(i, future=["Job Loss"]) for i in range(10)]
    readings = {r["theme"]: r["reading"] for r in build_survey(rows, ENGINE)["validation"]["comparison"]}
    assert readings["Failed instalments"] == "Untested"
    assert readings["Cash-flow fit"] == "Engine under-counts"      # 10 of 10 investors vs 3% of problem posts
    assert readings["Understanding returns and progress"] == "Supported"
    assert readings["Help outside the app"] == "Supported"


def test_no_survey_means_no_section():
    assert build_survey([], ENGINE) == {}
