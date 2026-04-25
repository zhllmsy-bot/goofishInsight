from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...category_compat import compatible_scope_keys, resolve_category_code
from ...db import session_scope
from ...models import Category, CategoryRuntimeProfile, Item, XianyuCategoryMapping
from ...pricing import title_matches_domain
from .catalog_category_quality import catalog_scope_mismatch_reason
from .raw_cate_policy_config import upsert_raw_cate_policy_config_with_session
from .xianyu_category_mapping import build_xianyu_category_match_key

SUPPORTED_AUTO_SUPPLEMENT_CATEGORY_CODES: tuple[str, ...] = (
    "apple_computer",
    "garmin_watch",
    "phone",
    "camera_body",
    "camera_interchangeable_lens",
)

LENS_FOCAL_PATTERN = re.compile(r"\b\d{1,3}(?:\s*-\s*\d{1,3})?\s*mm\b", re.IGNORECASE)
LENS_APERTURE_PATTERN = re.compile(r"\bf\s*/?\s*\d(?:\.\d)?\b", re.IGNORECASE)

APPLE_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("apple_tablet_or_pad", re.compile(r"(ipad|平板|matepad|mate pad|tablet)", re.IGNORECASE)),
    ("apple_watch_or_audio", re.compile(r"(apple watch|iwatch|watch series|airpods|耳机)", re.IGNORECASE)),
    (
        "apple_learning_device",
        re.compile(r"(复读机|听力机|听读神器|磨耳朵|学习机|点读笔|随身听|播放器|墨水屏阅读器|电子墨水屏)", re.IGNORECASE),
    ),
    (
        "apple_ticket_or_event",
        re.compile(r"(签售|名额|门票|入场|连载|广交会|活动票|演出|展会|席位)", re.IGNORECASE),
    ),
    (
        "apple_tv_or_display_device",
        re.compile(r"(电视|投屏盒子|车载导航|安卓盒子|carplay|tbox)", re.IGNORECASE),
    ),
    (
        "apple_bike_or_vehicle",
        re.compile(r"(电动自行车|自行车|机械师二代|车载|车型|问界|领克|租车行|租测|婚车)", re.IGNORECASE),
    ),
    (
        "apple_auto_or_vehicle",
        re.compile(
            r"(汽车|排气|阀门|中尾段|尾段|保险杠|车门|车源|租车|婚车|发动机|无损安装|保时捷|宝马|奔驰|奥迪|丰田|本田|路虎|福特|凯迪拉克)",
            re.IGNORECASE,
        ),
    ),
    (
        "apple_part_or_server",
        re.compile(r"(ssd|拆机硬盘|硬盘(?:扩容|小板|板|颗粒|芯片)?|扩容|主板|服务器|机架|阵列|双路|存储主机)", re.IGNORECASE),
    ),
    (
        "apple_accessory",
        re.compile(
            r"(防窥膜|键盘膜|保护膜|贴膜|防尘底座|底座|拓展坞|扩展坞|充电器|快充|充电头|电源适配器|适配器|数据线|保护壳|硅胶套|支架)",
            re.IGNORECASE,
        ),
    ),
    ("apple_display_bundle", re.compile(r"(studio display|显示器)", re.IGNORECASE)),
)
GARMIN_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("garmin_apple_watch", re.compile(r"(apple watch|iwatch|watch series)", re.IGNORECASE)),
    ("garmin_band_accessory", re.compile(r"(表带|腕带|心率带|表节)", re.IGNORECASE)),
    ("garmin_non_watch_device", re.compile(r"(探鱼器|导航仪|手持gps|手持机|码表|项圈|狗)", re.IGNORECASE)),
    ("garmin_accessory", re.compile(r"(充电线|转接头|电池|盖板|后盖|外屏|保护壳|支架|头灯)", re.IGNORECASE)),
)
PHONE_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "phone_packaging_only",
        re.compile(
            r"(空盒|包装盒|手机盒|只有盒子|只卖盒子|仅售原装空盒|不含手机|盒子内没有任何配件和手机)",
            re.IGNORECASE,
        ),
    ),
    (
        "phone_part_or_shell",
        re.compile(r"(主板|排线|尾插|听筒|摄像头|手机壳|保护壳|卡针|说明书|电池|屏幕)", re.IGNORECASE),
    ),
    ("phone_non_phone_device", re.compile(r"(apple watch|iwatch|ipad|平板|airpods|耳机)", re.IGNORECASE)),
    ("phone_auto_or_vehicle", re.compile(r"(汽车|租车|租赁|婚车|四驱|车源|改装排气|保险杠|车门)", re.IGNORECASE)),
)
CAMERA_BODY_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "camera_body_accessory_or_lens",
        re.compile(r"(镜头|转接环|滤镜|uv镜|遮光罩|相机包|闪光灯|补光灯|稳定器|兔笼|手柄|硅胶套|保护壳)", re.IGNORECASE),
    ),
)
LENS_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "lens_accessory",
        re.compile(r"(滤镜|uv镜|转接环|遮光罩|镜头盖|相机包|支架|接环)", re.IGNORECASE),
    ),
)
DOMAINLESS_REJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("domainless_apple_watch", re.compile(r"(apple watch|iwatch|watch series)", re.IGNORECASE)),
    ("domainless_tablet", re.compile(r"(ipad|平板|matepad|mate pad|tablet)", re.IGNORECASE)),
    ("domainless_server", re.compile(r"(服务器|机架|双路|阵列|存储主机)", re.IGNORECASE)),
    (
        "domainless_learning_device",
        re.compile(r"(复读机|听力机|听读神器|磨耳朵|学习机|点读笔|随身听|播放器|墨水屏阅读器|电子墨水屏)", re.IGNORECASE),
    ),
    (
        "domainless_ticket_or_event",
        re.compile(r"(签售|名额|门票|入场|连载|广交会|活动票|演出|展会|席位)", re.IGNORECASE),
    ),
    (
        "domainless_tv_or_box_device",
        re.compile(r"(电视|投屏盒子|车载导航|安卓盒子|carplay|tbox)", re.IGNORECASE),
    ),
    (
        "domainless_bike_or_vehicle",
        re.compile(r"(电动自行车|自行车|机械师二代|车载|车型|问界|领克|租车行|租测|婚车)", re.IGNORECASE),
    ),
    ("domainless_watch_accessory", re.compile(r"(表带|腕带|心率带|探鱼器|导航仪|手持gps|手持机)", re.IGNORECASE)),
    (
        "domainless_phone_packaging",
        re.compile(
            r"(空盒|包装盒|手机盒|只有盒子|只卖盒子|仅售原装空盒|不含手机|盒子内没有任何配件和手机)",
            re.IGNORECASE,
        ),
    ),
    ("domainless_phone_part", re.compile(r"(主板|排线|尾插|听筒|摄像头|手机壳|保护壳|卡针|说明书)", re.IGNORECASE)),
    ("domainless_camera_accessory", re.compile(r"(转接环|滤镜|uv镜|遮光罩|相机包|闪光灯|补光灯|稳定器|兔笼)", re.IGNORECASE)),
    (
        "domainless_computer_part",
        re.compile(r"(ssd|拆机硬盘|硬盘(?:扩容|小板|板|颗粒|芯片)?|扩容|主板)", re.IGNORECASE),
    ),
    (
        "domainless_auto_or_vehicle",
        re.compile(
            r"(汽车|排气|阀门|中尾段|尾段|保险杠|车门|车源|租车|婚车|发动机|无损安装|保时捷|宝马|奔驰|奥迪|丰田|本田|路虎|福特|凯迪拉克)",
            re.IGNORECASE,
        ),
    ),
)
NEUTRAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("neutral_wanted_or_buyback", re.compile(r"(^|\s)(求购|收一台|诚收|高价回收|现金回收|回收)", re.IGNORECASE)),
    ("neutral_rental", re.compile(r"(出租|租用|远程租|免押出租|租赁|可租测|可租)", re.IGNORECASE)),
)


class XianyuCategoryAutoSupplementError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AutoSupplementTarget:
    category_code: str
    category_id: str
    template_id: str


@dataclass(frozen=True, slots=True)
class AutoSupplementScopeCandidate:
    match_scope: str
    match_key: str
    item_count: int
    xianyu_cat_id: str | None = None
    xianyu_tb_cat_id: str | None = None
    xianyu_c_cat_id: str | None = None


def build_xianyu_category_auto_supplement_plan(
    *,
    category_code: str | None = None,
    sample_limit: int = 12,
) -> dict[str, Any]:
    with session_scope() as session:
        return build_xianyu_category_auto_supplement_plan_with_session(
            session,
            category_code=category_code,
            sample_limit=sample_limit,
        )


def build_xianyu_category_auto_supplement_plan_with_session(
    session: Session,
    *,
    category_code: str | None = None,
    sample_limit: int = 12,
) -> dict[str, Any]:
    target_codes = _resolve_target_category_codes(category_code)
    targets = _load_targets_with_session(session, category_codes=target_codes)
    active_match_keys = _load_active_match_keys_with_session(session)
    candidates = _discover_scope_candidates_with_session(session, category_codes=target_codes)

    proposals: list[dict[str, Any]] = []
    skipped_existing = 0
    for candidate in candidates:
        if candidate.match_key in active_match_keys:
            skipped_existing += 1
            continue
        sample_items = _load_scope_sample_items_with_session(session, candidate=candidate, sample_limit=sample_limit)
        observed_domain_counts = _load_candidate_business_domain_counts_with_session(session, candidate=candidate)
        proposal = _build_scope_proposal(
            candidate=candidate,
            sample_items=sample_items,
            observed_domain_counts=observed_domain_counts,
            targets=targets,
        )
        proposals.append(proposal)

    action_counts = Counter(str(proposal["action"]) for proposal in proposals)
    return {
        "filters": {
            "categoryCode": category_code,
            "sampleLimit": max(int(sample_limit), 1),
        },
        "targetCategoryCodes": list(target_codes),
        "candidateCount": len(candidates),
        "skippedExistingCount": skipped_existing,
        "proposalCount": len(proposals),
        "actionCounts": dict(sorted(action_counts.items())),
        "items": sorted(
            proposals,
            key=lambda row: (
                _proposal_action_rank(str(row["action"])),
                -int(row["candidateItemCount"]),
                str(row["matchKey"]),
            ),
        ),
    }


def apply_xianyu_category_auto_supplement(
    *,
    operator_id: str,
    category_code: str | None = None,
    sample_limit: int = 12,
    dry_run: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        result = apply_xianyu_category_auto_supplement_with_session(
            session,
            operator_id=operator_id,
            category_code=category_code,
            sample_limit=sample_limit,
            dry_run=dry_run,
        )
        if dry_run:
            session.rollback()
        return result


def apply_xianyu_category_auto_supplement_with_session(
    session: Session,
    *,
    operator_id: str,
    category_code: str | None = None,
    sample_limit: int = 12,
    dry_run: bool = True,
) -> dict[str, Any]:
    plan = build_xianyu_category_auto_supplement_plan_with_session(
        session,
        category_code=category_code,
        sample_limit=sample_limit,
    )
    persisted: list[dict[str, Any]] = []
    for proposal in list(plan.get("items") or []):
        payload = proposal.get("payload")
        if not isinstance(payload, dict):
            continue
        persisted_result = upsert_raw_cate_policy_config_with_session(
            session,
            payload=payload,
            operator_id=operator_id,
            dry_run=dry_run,
        )
        persisted.append(
            {
                "action": proposal["action"],
                "matchKey": proposal["matchKey"],
                "policy": persisted_result["policy"],
            }
        )

    return {
        **plan,
        "operatorId": operator_id,
        "dryRun": dry_run,
        "persistedCount": len(persisted),
        "persistedActionCounts": dict(sorted(Counter(row["action"] for row in persisted).items())),
        "persistedItems": persisted,
    }


def _build_scope_proposal(
    *,
    candidate: AutoSupplementScopeCandidate,
    sample_items: list[Item],
    observed_domain_counts: dict[str, int],
    targets: dict[str, AutoSupplementTarget],
) -> dict[str, Any]:
    evaluation = _evaluate_scope_items(sample_items, observed_domain_counts=observed_domain_counts)
    action = str(evaluation["action"])
    dominant_category_code = evaluation.get("dominantCategoryCode")
    payload = None
    if action == "FORCE_TEMPLATE" and dominant_category_code in targets:
        target = targets[str(dominant_category_code)]
        payload = {
            "matchScope": candidate.match_scope,
            "xianyuCatId": candidate.xianyu_cat_id,
            "xianyuTbCatId": candidate.xianyu_tb_cat_id,
            "xianyuCCatId": candidate.xianyu_c_cat_id,
            "categoryId": target.category_id,
            "templateId": target.template_id,
            "policyMode": "FORCE_TEMPLATE",
            "resolutionSource": "db_auto_supplement_v1",
            "confidence": evaluation["confidence"],
            "metadata": _build_policy_metadata(candidate=candidate, evaluation=evaluation),
        }
    elif action == "BLOCK":
        payload = {
            "matchScope": candidate.match_scope,
            "xianyuCatId": candidate.xianyu_cat_id,
            "xianyuTbCatId": candidate.xianyu_tb_cat_id,
            "xianyuCCatId": candidate.xianyu_c_cat_id,
            "policyMode": "BLOCK",
            "resolutionSource": "db_auto_supplement_v1",
            "confidence": evaluation["confidence"],
            "metadata": _build_policy_metadata(candidate=candidate, evaluation=evaluation),
        }

    return {
        "matchScope": candidate.match_scope,
        "matchKey": candidate.match_key,
        "xianyuCatId": candidate.xianyu_cat_id,
        "xianyuTbCatId": candidate.xianyu_tb_cat_id,
        "xianyuCCatId": candidate.xianyu_c_cat_id,
        "candidateItemCount": candidate.item_count,
        "sampleCount": len(sample_items),
        "sampleTitles": [str(item.title or "") for item in sample_items[:6]],
        "observedBusinessDomains": dict(sorted((key, int(value)) for key, value in observed_domain_counts.items() if key)),
        **evaluation,
        "payload": payload,
    }


def _build_policy_metadata(
    *,
    candidate: AutoSupplementScopeCandidate,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "db_auto_supplement_v1",
        "candidateItemCount": candidate.item_count,
        "positiveCategoryCounts": dict(evaluation.get("positiveCategoryCounts") or {}),
        "junkReasonCounts": dict(evaluation.get("junkReasonCounts") or {}),
        "neutralReasonCounts": dict(evaluation.get("neutralReasonCounts") or {}),
        "observedBusinessDomainCounts": dict(evaluation.get("observedBusinessDomainCounts") or {}),
        "observedDominantCategoryCode": evaluation.get("observedDominantCategoryCode"),
        "observedDominantCategoryRatio": evaluation.get("observedDominantCategoryRatio"),
        "unknownCount": int(evaluation.get("unknownCount") or 0),
        "sampleTitles": list(evaluation.get("sampleTitles") or []),
    }


def _evaluate_scope_items(
    items: list[Item],
    *,
    observed_domain_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    positive_counts: Counter[str] = Counter()
    junk_reason_counts: Counter[str] = Counter()
    neutral_reason_counts: Counter[str] = Counter()
    unknown_count = 0

    for item in items:
        title = str(item.title or "")
        assessment = _assess_title(title)
        kind = str(assessment["kind"])
        if kind == "positive":
            positive_counts[str(assessment["domain"])] += 1
        elif kind == "junk":
            junk_reason_counts[str(assessment["reason"])] += 1
        elif kind == "neutral":
            neutral_reason_counts[str(assessment["reason"])] += 1
        else:
            unknown_count += 1

    sample_count = len(items)
    dominant_category_code = None
    dominant_count = 0
    runner_up_count = 0
    if positive_counts:
        most_common = positive_counts.most_common(2)
        dominant_category_code = str(most_common[0][0])
        dominant_count = int(most_common[0][1])
        if len(most_common) > 1:
            runner_up_count = int(most_common[1][1])

    normalized_observed_domain_counts = _normalize_business_domain_counts(observed_domain_counts)
    observed_dominant_category_code = None
    observed_dominant_count = 0
    observed_runner_up_count = 0
    observed_total_count = sum(int(value) for value in normalized_observed_domain_counts.values())
    if normalized_observed_domain_counts:
        observed_common = normalized_observed_domain_counts.most_common(2)
        observed_dominant_category_code = str(observed_common[0][0])
        observed_dominant_count = int(observed_common[0][1])
        if len(observed_common) > 1:
            observed_runner_up_count = int(observed_common[1][1])

    junk_count = sum(junk_reason_counts.values())
    action = "REVIEW"
    confidence = 0.0
    if _qualifies_force_template(
        sample_count=sample_count,
        dominant_count=dominant_count,
        runner_up_count=runner_up_count,
        junk_count=junk_count,
    ) and _observed_counts_allow_sample_force_template(
        dominant_category_code=dominant_category_code,
        observed_dominant_category_code=observed_dominant_category_code,
        observed_dominant_count=observed_dominant_count,
        observed_total_count=observed_total_count,
    ):
        action = "FORCE_TEMPLATE"
        confidence = _safe_ratio(dominant_count, sample_count)
    elif _qualifies_force_template_from_observed_domains(
        sample_count=sample_count,
        dominant_category_code=dominant_category_code,
        dominant_count=dominant_count,
        runner_up_count=runner_up_count,
        junk_count=junk_count,
        observed_dominant_category_code=observed_dominant_category_code,
        observed_dominant_count=observed_dominant_count,
        observed_runner_up_count=observed_runner_up_count,
        observed_total_count=observed_total_count,
    ):
        action = "FORCE_TEMPLATE"
        confidence = max(
            _safe_ratio(dominant_count, sample_count),
            _safe_ratio(observed_dominant_count, observed_total_count),
        )
    elif _qualifies_block(
        sample_count=sample_count,
        dominant_count=dominant_count,
        junk_count=junk_count,
    ):
        action = "BLOCK"
        confidence = _safe_ratio(junk_count, sample_count)
    elif _qualifies_block_for_offscope_cluster(
        sample_count=sample_count,
        dominant_count=dominant_count,
        junk_count=junk_count,
        junk_reason_counts=junk_reason_counts,
        neutral_reason_counts=neutral_reason_counts,
    ):
        action = "BLOCK"
        confidence = max(
            _safe_ratio(junk_count, sample_count),
            _safe_ratio(sum(neutral_reason_counts.values()), sample_count),
        )
    elif dominant_count > 0:
        confidence = _safe_ratio(dominant_count, sample_count)
    elif junk_count > 0:
        confidence = _safe_ratio(junk_count, sample_count)

    return {
        "action": action,
        "confidence": confidence,
        "dominantCategoryCode": dominant_category_code,
        "positiveCategoryCounts": dict(sorted(positive_counts.items())),
        "junkReasonCounts": dict(sorted(junk_reason_counts.items())),
        "neutralReasonCounts": dict(sorted(neutral_reason_counts.items())),
        "observedBusinessDomainCounts": dict(sorted(normalized_observed_domain_counts.items())),
        "observedDominantCategoryCode": observed_dominant_category_code,
        "observedDominantCategoryRatio": _safe_ratio(observed_dominant_count, observed_total_count),
        "unknownCount": unknown_count,
        "sampleTitles": [str(item.title or "") for item in items[:6]],
    }


def _qualifies_force_template(
    *,
    sample_count: int,
    dominant_count: int,
    runner_up_count: int,
    junk_count: int,
) -> bool:
    if sample_count <= 0 or dominant_count <= 0:
        return False
    if sample_count < 3:
        return False
    required_count = max(2, math.ceil(sample_count * 0.7))
    allowed_junk = 0 if sample_count <= 2 else max(1, sample_count // 5)
    if dominant_count < required_count:
        return False
    if runner_up_count > 0 and dominant_count < runner_up_count * 3:
        return False
    return junk_count <= allowed_junk


def _qualifies_block(
    *,
    sample_count: int,
    dominant_count: int,
    junk_count: int,
) -> bool:
    if sample_count <= 0 or junk_count <= 0:
        return False
    if sample_count == 1:
        return False
    required_count = max(2, math.ceil(sample_count * 0.7))
    return junk_count >= required_count and dominant_count <= 1


def _qualifies_block_for_offscope_cluster(
    *,
    sample_count: int,
    dominant_count: int,
    junk_count: int,
    junk_reason_counts: Counter[str],
    neutral_reason_counts: Counter[str],
) -> bool:
    if sample_count < 5:
        return False
    rental_count = int(neutral_reason_counts.get("neutral_rental") or 0)
    if dominant_count == 0 and junk_count == 0 and rental_count >= max(4, math.ceil(sample_count * 0.8)):
        return True
    if dominant_count == 0 and junk_count >= max(3, math.ceil(sample_count * 0.5)):
        return True
    if junk_count >= max(6, math.ceil(sample_count * 0.65)) and dominant_count <= 2:
        return True
    top_junk_count = max((int(value) for value in junk_reason_counts.values()), default=0)
    if top_junk_count >= max(4, math.ceil(sample_count * 0.6)) and dominant_count <= max(4, math.ceil(sample_count * 0.35)):
        return True
    return False


def _qualifies_force_template_from_observed_domains(
    *,
    sample_count: int,
    dominant_category_code: str | None,
    dominant_count: int,
    runner_up_count: int,
    junk_count: int,
    observed_dominant_category_code: str | None,
    observed_dominant_count: int,
    observed_runner_up_count: int,
    observed_total_count: int,
) -> bool:
    if observed_total_count < 10 or observed_dominant_count < 10:
        return False
    if dominant_category_code is None or observed_dominant_category_code is None:
        return False
    if dominant_category_code != observed_dominant_category_code:
        return False
    if _safe_ratio(observed_dominant_count, observed_total_count) < 0.9:
        return False
    if dominant_count < max(3, math.ceil(sample_count * 0.4)):
        return False
    if runner_up_count > 0 and dominant_count < runner_up_count * 2:
        return False
    allowed_junk = max(3, sample_count // 3)
    if junk_count > allowed_junk or junk_count >= dominant_count:
        return False
    if observed_runner_up_count > 0 and observed_dominant_count < observed_runner_up_count * 4:
        return False
    return True


def _observed_counts_allow_sample_force_template(
    *,
    dominant_category_code: str | None,
    observed_dominant_category_code: str | None,
    observed_dominant_count: int,
    observed_total_count: int,
) -> bool:
    if observed_total_count <= 0:
        return True
    if dominant_category_code is None or observed_dominant_category_code is None:
        return False
    if dominant_category_code != observed_dominant_category_code:
        return False
    if observed_total_count < 10:
        return _safe_ratio(observed_dominant_count, observed_total_count) >= 0.9
    return True


def _assess_title(title: str | None) -> dict[str, str | None]:
    normalized_title = _normalize_title(title)
    if not normalized_title:
        return {"kind": "unknown", "reason": "missing_title", "domain": None}

    neutral_reason = _first_matching_reason(normalized_title, NEUTRAL_PATTERNS)
    if neutral_reason is not None:
        return {"kind": "neutral", "reason": neutral_reason, "domain": None}

    positive_domains: list[str] = []
    rejected_domains: list[str] = []
    for category_code in SUPPORTED_AUTO_SUPPLEMENT_CATEGORY_CODES:
        if not _matches_category_code(category_code, normalized_title):
            continue
        reject_reason = _reject_reason_for_category_code(category_code, normalized_title)
        if reject_reason is not None:
            rejected_domains.append(reject_reason)
            continue
        positive_domains.append(category_code)

    if len(positive_domains) == 1:
        return {"kind": "positive", "reason": None, "domain": positive_domains[0]}
    if len(positive_domains) > 1:
        return {"kind": "unknown", "reason": "multi_domain_match", "domain": None}
    if rejected_domains:
        return {"kind": "junk", "reason": sorted(rejected_domains)[0], "domain": None}

    domainless_reason = _first_matching_reason(normalized_title, DOMAINLESS_REJECT_PATTERNS)
    if domainless_reason is not None:
        return {"kind": "junk", "reason": domainless_reason, "domain": None}
    return {"kind": "unknown", "reason": "no_supported_domain_match", "domain": None}


def _matches_category_code(category_code: str, normalized_title: str) -> bool:
    if category_code == "apple_computer":
        return _looks_like_apple_computer_title(normalized_title)
    if category_code == "garmin_watch":
        return _looks_like_garmin_watch_title(normalized_title)
    if category_code == "phone":
        return _looks_like_phone_title(normalized_title)
    if category_code == "camera_body":
        return _looks_like_camera_body_title(normalized_title)
    if category_code == "camera_interchangeable_lens":
        return _looks_like_lens_title(normalized_title)
    return False


def _reject_reason_for_category_code(category_code: str, normalized_title: str) -> str | None:
    mismatch_reason = None
    if category_code in {"apple_computer", "garmin_watch", "phone"}:
        mismatch_reason = catalog_scope_mismatch_reason(category_code, title=normalized_title)
    if mismatch_reason:
        return str(mismatch_reason)
    if category_code == "apple_computer":
        return _apple_reject_reason(normalized_title)
    if category_code == "garmin_watch":
        return _garmin_reject_reason(normalized_title)
    if category_code == "phone":
        return _first_matching_reason(normalized_title, PHONE_REJECT_PATTERNS)
    if category_code == "camera_body":
        return _camera_body_reject_reason(normalized_title)
    if category_code == "camera_interchangeable_lens":
        return _lens_reject_reason(normalized_title)
    return None


def _looks_like_apple_computer_title(normalized_title: str) -> bool:
    return title_matches_domain("apple_computer", normalized_title)


def _apple_reject_reason(normalized_title: str) -> str | None:
    reject_reason = _first_matching_reason(normalized_title, APPLE_REJECT_PATTERNS)
    if reject_reason != "apple_accessory":
        return reject_reason
    strong_product = _looks_like_apple_computer_title(normalized_title)
    included_accessory = bool(
        re.search(r"(带|送|含|配).{0,12}(盒子|包装|电源线|充电器|数据线|拓展坞|扩展坞|保护壳|硅胶套|支架)", normalized_title)
    )
    if strong_product and included_accessory:
        return None
    return reject_reason


def _looks_like_garmin_watch_title(normalized_title: str) -> bool:
    return any(
        token in normalized_title
        for token in ("garmin", "佳明", "fenix", "forerunner", "instinct", "epix", "marq", "venu", "approach", "tactix", "enduro", "descent")
    )


def _garmin_reject_reason(normalized_title: str) -> str | None:
    reject_reason = _first_matching_reason(normalized_title, GARMIN_REJECT_PATTERNS)
    if reject_reason not in {"garmin_accessory", "garmin_band_accessory"}:
        return reject_reason
    strong_product = _looks_like_garmin_watch_title(normalized_title)
    included_accessory = bool(re.search(r"(带|送|含|配).{0,12}(表带|充电线|盒子|包装|保护壳|支架|充电器)", normalized_title))
    if strong_product and included_accessory:
        return None
    return reject_reason


def _looks_like_phone_title(normalized_title: str) -> bool:
    if "iphone" in normalized_title or "手机" in normalized_title:
        return True
    phone_patterns = (
        re.compile(r"\bmate\s*\d{2}", re.IGNORECASE),
        re.compile(r"\bpura\s*\d{2}", re.IGNORECASE),
        re.compile(r"\bmi\s*\d{2}", re.IGNORECASE),
        re.compile(r"小米\s*\d{1,2}", re.IGNORECASE),
        re.compile(r"redmi\s*[knx]?\d", re.IGNORECASE),
        re.compile(r"find\s*x\d", re.IGNORECASE),
        re.compile(r"\bvivo\s*x\d", re.IGNORECASE),
        re.compile(r"\biqoo\s*\d", re.IGNORECASE),
        re.compile(r"荣耀\s*\d", re.IGNORECASE),
        re.compile(r"\bhonor\s*\d", re.IGNORECASE),
        re.compile(r"galaxy\s*s\d", re.IGNORECASE),
        re.compile(r"\bsamsung\s*s\d", re.IGNORECASE),
        re.compile(r"\bpixel\s*\d", re.IGNORECASE),
        re.compile(r"oneplus\s*\d", re.IGNORECASE),
        re.compile(r"一加\s*\d", re.IGNORECASE),
    )
    return any(pattern.search(normalized_title) for pattern in phone_patterns)


def _looks_like_lens_title(normalized_title: str) -> bool:
    return title_matches_domain("camera_interchangeable_lens", normalized_title)


def _lens_reject_reason(normalized_title: str) -> str | None:
    accessory_reason = _first_matching_reason(normalized_title, LENS_REJECT_PATTERNS)
    if accessory_reason is None:
        return None
    strong_lens_product = bool(LENS_FOCAL_PATTERN.search(normalized_title) and LENS_APERTURE_PATTERN.search(normalized_title))
    included_accessory = bool(re.search(r"(带|送|含|配).{0,8}(uv镜|滤镜|前后盖|前盖|后盖|遮光罩)", normalized_title))
    if strong_lens_product and included_accessory:
        return None
    return accessory_reason


def _looks_like_camera_body_title(normalized_title: str) -> bool:
    return title_matches_domain("camera_body", normalized_title)


def _camera_body_reject_reason(normalized_title: str) -> str | None:
    reject_reason = _first_matching_reason(normalized_title, CAMERA_BODY_REJECT_PATTERNS)
    if reject_reason is None:
        return None
    strong_product = _looks_like_camera_body_title(normalized_title)
    included_accessory = bool(
        re.search(r"(带|送|含|配).{0,12}(手柄|相机包|闪光灯|补光灯|稳定器|兔笼|电池|肩带)", normalized_title)
        or re.search(r"(不含镜头|镜头另售|镜头另出|不带镜头)", normalized_title)
    )
    if strong_product and included_accessory:
        return None
    return reject_reason


def _compact_contains_mac_signal(normalized_title: str) -> bool:
    compact = re.sub(r"[\s\-_+/（）()]+", "", normalized_title)
    strong_tokens = (
        "macbook",
        "macbookair",
        "macbookpro",
        "macmini",
        "macstudio",
        "imac",
        "苹果",
        "apple",
    )
    if any(token in compact for token in strong_tokens):
        return True
    chip_match = re.search(r"m[1-4](?:pro|max|ultra)?", compact)
    if chip_match is None:
        return False
    return any(token in compact for token in ("mac", "book", "studio", "mini", "imac", "苹果", "apple"))


def _first_matching_reason(
    normalized_title: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> str | None:
    for reason, pattern in patterns:
        if pattern.search(normalized_title):
            return reason
    return None


def _normalize_title(value: str | None) -> str:
    return str(value or "").strip().lower()


def _resolve_target_category_codes(category_code: str | None) -> tuple[str, ...]:
    if category_code is None:
        return SUPPORTED_AUTO_SUPPLEMENT_CATEGORY_CODES
    resolved = resolve_category_code(category_code)
    if resolved not in SUPPORTED_AUTO_SUPPLEMENT_CATEGORY_CODES:
        raise XianyuCategoryAutoSupplementError(f"Unsupported category_code: {category_code}")
    return (resolved,)


def _load_targets_with_session(
    session: Session,
    *,
    category_codes: tuple[str, ...],
) -> dict[str, AutoSupplementTarget]:
    rows = session.execute(
        select(Category.code, Category.id, CategoryRuntimeProfile.active_template_id)
        .join(CategoryRuntimeProfile, CategoryRuntimeProfile.category_id == Category.id)
        .where(
            Category.code.in_(category_codes),
            CategoryRuntimeProfile.active_template_id.is_not(None),
            CategoryRuntimeProfile.status == "ACTIVE",
        )
    ).all()
    targets = {
        str(code): AutoSupplementTarget(
            category_code=str(code),
            category_id=str(category_id),
            template_id=str(template_id),
        )
        for code, category_id, template_id in rows
        if code and category_id and template_id
    }
    missing = [code for code in category_codes if code not in targets]
    if missing:
        raise XianyuCategoryAutoSupplementError(
            "Missing active runtime template for category_code(s): " + ", ".join(sorted(missing))
        )
    return targets


def _discover_scope_candidates_with_session(
    session: Session,
    *,
    category_codes: tuple[str, ...],
) -> list[AutoSupplementScopeCandidate]:
    scope_keys = sorted({scope_key for code in category_codes for scope_key in compatible_scope_keys(code)})
    if not scope_keys:
        return []

    base_filters = (
        Item.source_platform == "xianyu",
        Item.business_domain.in_(scope_keys),
        or_(
            Item.xianyu_c_cat_id.is_not(None),
            Item.xianyu_cat_id.is_not(None),
            Item.xianyu_tb_cat_id.is_not(None),
        ),
    )

    candidates: list[AutoSupplementScopeCandidate] = []
    cat_tb_rows = session.execute(
        select(Item.xianyu_cat_id, Item.xianyu_tb_cat_id, func.count())
        .where(
            *base_filters,
            Item.xianyu_cat_id.is_not(None),
            Item.xianyu_tb_cat_id.is_not(None),
        )
        .group_by(Item.xianyu_cat_id, Item.xianyu_tb_cat_id)
    ).all()
    for cat_id, tb_cat_id, item_count in cat_tb_rows:
        match_key = build_xianyu_category_match_key(
            match_scope="CAT_TB",
            xianyu_cat_id=str(cat_id),
            xianyu_tb_cat_id=str(tb_cat_id),
        )
        candidates.append(
            AutoSupplementScopeCandidate(
                match_scope="CAT_TB",
                match_key=match_key,
                item_count=int(item_count or 0),
                xianyu_cat_id=str(cat_id),
                xianyu_tb_cat_id=str(tb_cat_id),
            )
        )

    c_cat_rows = session.execute(
        select(Item.xianyu_c_cat_id, func.count())
        .where(
            *base_filters,
            Item.xianyu_c_cat_id.is_not(None),
            or_(Item.xianyu_cat_id.is_(None), Item.xianyu_tb_cat_id.is_(None)),
        )
        .group_by(Item.xianyu_c_cat_id)
    ).all()
    for c_cat_id, item_count in c_cat_rows:
        match_key = build_xianyu_category_match_key(
            match_scope="C_CAT",
            xianyu_c_cat_id=str(c_cat_id),
        )
        candidates.append(
            AutoSupplementScopeCandidate(
                match_scope="C_CAT",
                match_key=match_key,
                item_count=int(item_count or 0),
                xianyu_c_cat_id=str(c_cat_id),
            )
        )

    return sorted(candidates, key=lambda row: (-row.item_count, row.match_scope, row.match_key))


def _load_scope_sample_items_with_session(
    session: Session,
    *,
    candidate: AutoSupplementScopeCandidate,
    sample_limit: int,
) -> list[Item]:
    limit = max(int(sample_limit), 1)
    stmt = select(Item).where(Item.source_platform == "xianyu")
    if candidate.match_scope == "CAT_TB":
        stmt = stmt.where(
            Item.xianyu_cat_id == candidate.xianyu_cat_id,
            Item.xianyu_tb_cat_id == candidate.xianyu_tb_cat_id,
        )
    else:
        stmt = stmt.where(Item.xianyu_c_cat_id == candidate.xianyu_c_cat_id)
    rows = session.execute(stmt.order_by(Item.last_seen_at.desc(), Item.id.desc()).limit(limit)).scalars().all()
    return list(rows)


def _load_active_match_keys_with_session(session: Session) -> set[str]:
    rows = session.execute(
        select(XianyuCategoryMapping.match_key).where(XianyuCategoryMapping.status == "ACTIVE")
    ).all()
    return {str(match_key) for match_key, in rows if match_key}


def _load_candidate_business_domain_counts_with_session(
    session: Session,
    *,
    candidate: AutoSupplementScopeCandidate,
) -> dict[str, int]:
    stmt = (
        select(Item.business_domain, func.count())
        .where(Item.source_platform == "xianyu")
        .group_by(Item.business_domain)
    )
    if candidate.match_scope == "CAT_TB":
        stmt = stmt.where(
            Item.xianyu_cat_id == candidate.xianyu_cat_id,
            Item.xianyu_tb_cat_id == candidate.xianyu_tb_cat_id,
        )
    else:
        stmt = stmt.where(Item.xianyu_c_cat_id == candidate.xianyu_c_cat_id)
    rows = session.execute(stmt).all()
    normalized = _normalize_business_domain_counts({str(key): int(value or 0) for key, value in rows if key})
    return dict(sorted(normalized.items()))


def _normalize_business_domain_counts(
    observed_domain_counts: dict[str, int] | None,
) -> Counter[str]:
    normalized: Counter[str] = Counter()
    for domain, count in dict(observed_domain_counts or {}).items():
        canonical = resolve_category_code(domain) or str(domain or "")
        if not canonical:
            continue
        normalized[str(canonical)] += int(count or 0)
    return normalized


def _proposal_action_rank(action: str) -> int:
    if action == "FORCE_TEMPLATE":
        return 0
    if action == "BLOCK":
        return 1
    return 2


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


__all__ = [
    "SUPPORTED_AUTO_SUPPLEMENT_CATEGORY_CODES",
    "XianyuCategoryAutoSupplementError",
    "apply_xianyu_category_auto_supplement",
    "apply_xianyu_category_auto_supplement_with_session",
    "build_xianyu_category_auto_supplement_plan",
    "build_xianyu_category_auto_supplement_plan_with_session",
]
