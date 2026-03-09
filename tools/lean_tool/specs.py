"""
Gebündelte Lean-Spezifikationen für lokale und CI-Verifikation.
"""

from __future__ import annotations

BUILTIN_SPECS: dict[str, str] = {
    "progress_in_bounds": """\
import Mathlib

-- Invariante: 0 ≤ progress ≤ 1 wenn completed ≤ total und total > 0
-- Quelle: orchestration/goal_queue_manager.py:161
theorem progress_in_bounds (completed total : ℕ) (h : completed ≤ total) (ht : 0 < total) :
    (completed : ℝ) / (total : ℝ) ≤ 1 := by
  rw [div_le_one (by exact_mod_cast ht)]
  exact_mod_cast h
""",
    "keyword_bonus_cap": """\
import Mathlib

-- Invariante: min (x * 0.05) 0.3 ≤ 0.3  →  keyword_bonus niemals > 0.3
-- Quelle: tools/deep_research/tool.py:880
theorem keyword_bonus_cap (x : ℝ) :
    min (x * 0.05) 0.3 ≤ 0.3 :=
  min_le_right _ _
""",
    "arxiv_boundary": """\
import Mathlib

-- Invariante: relevance == threshold → akzeptiert (¬ relevance < threshold)
-- Quelle: tools/deep_research/trend_researcher.py:82
theorem arxiv_boundary (n : ℤ) : ¬ n < n :=
  lt_irrefl n
""",
    "soul_clamp_in_bounds": """\
import Mathlib

-- Invariante: Soul-Achsen clamp(v) = max 5 (min 95 v) bleibt immer in [5, 95]
-- Quelle: memory/soul_engine.py:259
theorem soul_clamp_in_bounds (v : ℝ) :
    5 ≤ max 5 (min 95 v) ∧ max 5 (min 95 v) ≤ 95 :=
  ⟨le_max_left 5 _, max_le (by norm_num) (min_le_left 95 v)⟩
""",
    "blackboard_ttl_positive": """\
import Mathlib

-- Invariante: TTL immer ≥ 1 Minute — max 1 ttl_minutes verhindert 0 oder negativ
-- Quelle: memory/agent_blackboard.py:108
theorem blackboard_ttl_positive (t : ℤ) : 1 ≤ max 1 t :=
  le_max_left 1 t
""",
    "success_rate_bounded": """\
import Mathlib

-- Invariante: AVG(success) ∈ [0, 1] wenn 0 ≤ sum ≤ n und n > 0
-- Quelle: orchestration/self_improvement_engine.py:299
theorem success_rate_bounded (n : ℕ) (s : ℝ)
    (hn : 0 < n) (hs_lo : 0 ≤ s) (hs_hi : s ≤ ↑n) :
    0 ≤ s / ↑n ∧ s / ↑n ≤ 1 := by
  have hn' : (0 : ℝ) < ↑n := Nat.cast_pos.mpr hn
  exact ⟨div_nonneg hs_lo hn'.le, (div_le_one hn').mpr hs_hi⟩
""",
    "m8_reflection_guard": """\
import Mathlib

-- Invariante: Session-Reflexion feuert nur wenn gap ≥ IDLE_THRESHOLD_MIN
-- h: gap < threshold → Reflexion wird NICHT ausgelöst
-- Quelle: orchestration/session_reflection.py:112
theorem m8_reflection_guard (gap threshold : ℝ) (h : gap < threshold) :
    ¬ threshold ≤ gap :=
  not_le.mpr h
""",
    "ambient_score_in_bounds": """\
import Mathlib

-- Invariante: Score ∈ [0, 1] nach Clamp (max 0 (min 1 score))
-- Quelle: orchestration/ambient_context_engine.py (AmbientSignal.score)
theorem ambient_score_in_bounds (score : ℝ) :
    0 ≤ max 0 (min 1 score) ∧ max 0 (min 1 score) ≤ 1 :=
  ⟨le_max_left 0 _, max_le (by norm_num) (min_le_left 1 score)⟩
""",
    "ambient_threshold_gate": """\
import Mathlib

-- Invariante: score < threshold → kein Task erstellt (¬ threshold ≤ score)
-- Quelle: orchestration/ambient_context_engine.py:_process_signal
theorem ambient_threshold_gate (score threshold : ℝ) (h : score < threshold) :
    ¬ threshold ≤ score := not_le.mpr h
""",
    "ambient_confirm_guard": """\
import Mathlib

-- Invariante: score < confirm_thresh → kein Telegram-Push
-- Quelle: orchestration/ambient_context_engine.py:_process_signal
theorem ambient_confirm_guard (score confirm_thresh : ℝ) (h : score < confirm_thresh) :
    ¬ confirm_thresh ≤ score := not_le.mpr h
""",
    "m16_weighted_avg_in_bounds": """\
import Mathlib

-- M16: Hook-Weight Konvergenz — gewichteter Durchschnitt pos/(pos+neg) ∈ [0, 1]
-- Zeigt dass der Feedback-Ratio immer bounded bleibt
-- Quelle: orchestration/feedback_engine.py:get_hook_stats
theorem m16_weighted_avg_in_bounds (pos neg total : ℝ)
    (hp : 0 ≤ pos) (hn : 0 ≤ neg) (ht : pos + neg = total) (htpos : 0 < total) :
    0 ≤ pos / total ∧ pos / total ≤ 1 := by
  constructor
  · exact div_nonneg hp (le_of_lt htpos)
  · rw [div_le_one htpos]; linarith
""",
    "m16_feedback_ratio": """\
import Mathlib

-- M16: Feedback-Ratio — pos_rate + neg_rate ≤ 1 (neutral = Rest)
-- Quelle: orchestration/feedback_engine.py:get_hook_stats
theorem m16_feedback_ratio (pos neg total : ℝ)
    (hp : 0 ≤ pos) (hn : 0 ≤ neg) (ht : pos + neg ≤ total) (htpos : 0 < total) :
    pos / total + neg / total ≤ 1 := by
  rw [div_add_div_same, div_le_one htpos]; linarith
""",
}


def build_combined_mathlib_specs() -> str:
    sections = ["import Mathlib", ""]
    for spec in BUILTIN_SPECS.values():
        lines = [line for line in spec.splitlines() if line.strip() != "import Mathlib"]
        sections.extend(lines)
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"
