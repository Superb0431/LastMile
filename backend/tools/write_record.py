"""写入用户画像或病历记录。"""

from pathlib import Path
from typing import Optional

from backend.config import USERS_DIR
from backend.memory import db


def _profile_path(username: str) -> Path:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "profile.md"


def run_write_record(
    username: str,
    target: str,
    content: str = "",
    visit_date: str = "",
    diagnosis: str = "",
    chief_complaint: str = "",
    exam_results: str = "",
    treatment: str = "",
    notes: str = "",
    symptom_date: str = "",
    symptoms: str = "",
    record_date: str = "",
) -> str:

    target = (target or "").strip().lower()
    record_date_val: Optional[str] = record_date.strip() if record_date and record_date.strip() else None

    if target == "profile":
        return _write_profile(username, content)
    if target == "ehr":
        return _write_ehr(
            username,
            visit_date=visit_date,
            diagnosis=diagnosis,
            chief_complaint=chief_complaint,
            exam_results=exam_results,
            treatment=treatment,
            notes=notes,
            record_date=record_date_val,
        )
    if target == "interval":
        return _write_interval(
            username,
            symptom_date=symptom_date,
            symptoms=symptoms,
            record_date=record_date_val,
        )
    return f"（未知的写入目标：{target}，请使用 profile / ehr / interval。）"


def _write_profile(username: str, content: str) -> str:
    if not content or not content.strip():
        return "（profile 内容为空，已跳过。）"
    file_path = _profile_path(username)
    with open(file_path, "a", encoding="utf-8") as f:
        if file_path.stat().st_size == 0:
            f.write(f"# {username} 的用户画像\n\n")
        f.write(f"- {content.strip()}\n")
    return f"已更新用户画像：{content.strip()}"


def _write_ehr(
    username: str,
    visit_date: str,
    diagnosis: str = "",
    chief_complaint: str = "",
    exam_results: str = "",
    treatment: str = "",
    notes: str = "",
    record_date: Optional[str] = None,
) -> str:
    if not visit_date or not visit_date.strip():
        return "（ehr 写入失败：到院日期 visit_date 不能为空。）"
    record_id = db.add_ehr_record(
        username=username,
        visit_date=visit_date.strip(),
        diagnosis=diagnosis.strip() if diagnosis else "未知",
        chief_complaint=chief_complaint or "",
        exam_results=exam_results or "",
        treatment=treatment or "",
        notes=notes or "",
        record_date=record_date,
    )
    return f"已写入 EHR 就诊记录（id={record_id}），到院日期：{visit_date.strip()}"


def _write_interval(
    username: str,
    symptom_date: str,
    symptoms: str,
    record_date: Optional[str] = None,
) -> str:
    if not symptom_date or not symptom_date.strip():
        return "（interval 写入失败：symptom_date 不能为空。）"
    if not symptoms or not symptoms.strip():
        return "（interval 写入失败：symptoms 不能为空。）"
    record_id = db.add_interval_record(
        username=username,
        symptom_date=symptom_date.strip(),
        symptoms=symptoms.strip(),
        record_date=record_date,
    )
    return f"已写入 Interval 症状记录（id={record_id}），日期：{symptom_date.strip()}"


WRITE_RECORD_FULL_INSTRUCTION = """
write_record 工具完整说明：
  target（必填）：profile | ehr | interval

  target=profile 时：
    - content（必填）：要追加的基本个人信息（身高、体重、年龄、性别、过敏史、慢性病、正在服用的药物等）
    - 仅当出现新的慢性病、过敏史、身高体重、用药状态时才更新 profile
    - content 只写新信息本身，不要加「记录了」「Profile」「用户表示」等前缀或说明

  target=ehr 时（用户表示去了医院）：
    - visit_date（必填）：到院日期；患者明确说了则用其表述，否则用【当前对话日期】
    - diagnosis：诊断疾病，未知可填「未知」
    - chief_complaint：主诉
    - exam_results：检查结果
    - treatment：医生处置
    - notes：备注

  target=interval 时（用户描述症状但未就诊）：
    - symptom_date（必填）：症状日期；患者明确说了则用其表述，否则用【当前对话日期】
    - symptoms（必填）：症状描述
""".strip()
