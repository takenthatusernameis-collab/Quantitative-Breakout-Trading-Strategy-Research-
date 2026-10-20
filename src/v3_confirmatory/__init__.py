"""v3 confirmatory evaluation execution path.

This package lives outside the hashed set (src/breakout_research) and outside
the v3 selection path (src/v3_campaign). It is the implementation of the
v3 confirmatory evaluation: at most one bounded run over the four published
candidates on the v3 confirmatory window.

Nothing in this package reads a confirmatory-window candle when it is
imported: the readiness probe is implemented but never executed in the session
that delivers it, and the run itself is refused unless the versioned
authorization permits it and the window exists.
"""

from __future__ import annotations

from .artifacts import (
    EVALUATION_WINDOW_RULE,
    build_checkpoint,
    build_ledger,
    build_result_rows,
    build_results_manifest,
    render_report_markdown,
)
from .benchmark import (
    ALIGNMENT_REFERENCE,
    ALIGNMENT_RULE,
    BENCHMARK_SYMBOL,
    FAIL_CLOSED_REASONS,
    alignment_report,
    assert_window_alignment,
    assert_window_benchmark_is_not_the_development_series,
    benchmark_required_for,
)
from .data import (
    build_window_manifest,
    inside_window,
    parse_dataset_csv,
    render_dataset_csv,
    retrieve_window_candles,
    verify_window_dataset,
)
from .errors import (
    AttemptBudgetError,
    AuthorizationError,
    BenchmarkAlignmentError,
    BoundsError,
    ConfirmatoryError,
    DataVerificationError,
    ScopeError,
    WindowExposureError,
    WindowNotReadyError,
)
from .exposure import (
    empty_state,
    register_exposure,
    window_is_spent,
)
from .identity import (
    canonical_source_digest,
    code_hash_amendment_path,
    code_identity_document,
    execution_path_digest,
    hashed_set_digest,
    load_code_hash_amendment,
    resolve_code_identity,
    run_code_identity,
)
from .report import (
    asset_outcome,
    build_report,
    report_outcome,
    specification_verdict,
)
from .runner import (
    DEFAULT_PATHS,
    FORBIDDEN_OUTPUT_PATHS,
    Plan,
    Workspace,
    build_plan,
    default_workspace,
    evaluate_preconditions,
    evaluate_window,
    run_confirmatory,
)
from .scope import evaluation_scope, selected_configurations
from .window import (
    MIN_WINDOW_HOURS,
    metadata_probe,
    parse_utc_ms,
    readiness,
    window_bounds,
)

__all__ = [
    "ALIGNMENT_REFERENCE",
    "ALIGNMENT_RULE",
    "AttemptBudgetError",
    "AuthorizationError",
    "BENCHMARK_SYMBOL",
    "BenchmarkAlignmentError",
    "BoundsError",
    "ConfirmatoryError",
    "DEFAULT_PATHS",
    "DataVerificationError",
    "EVALUATION_WINDOW_RULE",
    "FAIL_CLOSED_REASONS",
    "FORBIDDEN_OUTPUT_PATHS",
    "MIN_WINDOW_HOURS",
    "Plan",
    "ScopeError",
    "WindowExposureError",
    "WindowNotReadyError",
    "Workspace",
    "alignment_report",
    "assert_window_alignment",
    "assert_window_benchmark_is_not_the_development_series",
    "asset_outcome",
    "benchmark_required_for",
    "build_checkpoint",
    "build_ledger",
    "build_plan",
    "build_report",
    "build_result_rows",
    "build_results_manifest",
    "build_window_manifest",
    "canonical_source_digest",
    "code_hash_amendment_path",
    "code_identity_document",
    "default_workspace",
    "empty_state",
    "evaluation_scope",
    "evaluate_preconditions",
    "evaluate_window",
    "execution_path_digest",
    "hashed_set_digest",
    "inside_window",
    "load_code_hash_amendment",
    "metadata_probe",
    "parse_dataset_csv",
    "parse_utc_ms",
    "readiness",
    "register_exposure",
    "render_dataset_csv",
    "render_report_markdown",
    "report_outcome",
    "resolve_code_identity",
    "retrieve_window_candles",
    "run_code_identity",
    "run_confirmatory",
    "selected_configurations",
    "specification_verdict",
    "verify_window_dataset",
    "window_bounds",
    "window_is_spent",
]
__version__ = "1.0.0"
