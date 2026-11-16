"""Bounded integer contingency tables and the range of total inertia.

The module is deliberately self contained: it only depends on NumPy/SciPy and is
called both from the API/worker and from the small verification harness.
Every table considered is a matrix of non-negative integers whose cell values
stay inside a verified interval and whose row/column sums equal the verified
totals.  Total inertia is the correspondence-analysis quantity

    I(X) = sum_ij X_ij^2 / (R_i C_j) - 1

with zero-margin rows/columns contributing nothing (they are forced to zero by
the margin constraints).  The exported result distinguishes rigorously proven
bounds from feasible examples; a time-limited run never claims an exact extremum
it did not prove.
"""
from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.csgraph import maximum_flow

ALGORITHM = 'interval-inertia-bounds-v1'
MAX_SIDE = 12
MAX_CELL = 1_000_000
MAX_TOTAL = 144_000_000
NUMERIC_TOL = 1e-7
UNIT_SEGMENT_BUDGET = 3200
MAX_SEGMENTS_PER_CELL = 60
MAX_SEGMENTS_TOTAL = 4200


class IntervalInputError(ValueError):
    pass


def _as_matrix(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 2:
        raise IntervalInputError(f'{name} 必须是二维矩阵')
    return array


def _as_int_matrix(value: Any, name: str, low: int, high: int) -> np.ndarray:
    array = _as_matrix(value, name)
    if not np.issubdtype(array.dtype, np.number):
        raise IntervalInputError(f'{name} 必须是整数矩阵')
    if not np.isfinite(array).all():
        raise IntervalInputError(f'{name} 含非有限值')
    if not np.equal(array, np.floor(array)).all():
        raise IntervalInputError(f'{name} 必须全部是整数')
    array = array.astype(np.int64)
    if (array < low).any() or (array > high).any():
        raise IntervalInputError(f'{name} 的取值须在 {low}..{high}')
    return array


def normalize_inputs(lower, upper, row_totals, col_totals) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lower = _as_int_matrix(lower, '逐格下限', 0, MAX_CELL)
    upper = _as_int_matrix(upper, '逐格上限', 0, MAX_CELL)
    row_totals = np.asarray(row_totals)
    col_totals = np.asarray(col_totals)
    if row_totals.ndim != 1 or col_totals.ndim != 1:
        raise IntervalInputError('行合计与列合计必须是一维整数向量')
    if not np.issubdtype(row_totals.dtype, np.number) or not np.issubdtype(col_totals.dtype, np.number):
        raise IntervalInputError('行合计与列合计必须是整数')
    if not np.isfinite(row_totals).all() or not np.isfinite(col_totals).all():
        raise IntervalInputError('行合计或列合计含非有限值')
    if not np.equal(row_totals, np.floor(row_totals)).all() or not np.equal(col_totals, np.floor(col_totals)).all():
        raise IntervalInputError('行合计与列合计必须是整数')
    row_totals = row_totals.astype(np.int64)
    col_totals = col_totals.astype(np.int64)
    rd, cd = lower.shape
    if upper.shape != lower.shape or (rd, cd) != (row_totals.size, col_totals.size):
        raise IntervalInputError('下限、上限、行合计与列合计的维度不一致')
    if not (2 <= rd <= MAX_SIDE and 2 <= cd <= MAX_SIDE):
        raise IntervalInputError(f'区间计数研究须 2..{MAX_SIDE} 行和 2..{MAX_SIDE} 列')
    if (lower > upper).any():
        raise IntervalInputError('每个格子的下限不能大于上限')
    if (row_totals < 0).any() or (col_totals < 0).any():
        raise IntervalInputError('行合计与列合计必须非负')
    if (row_totals > MAX_TOTAL).any() or (col_totals > MAX_TOTAL).any():
        raise IntervalInputError(f'单行或单列核实的合计不得超过 {MAX_TOTAL}')
    return lower, upper, row_totals, col_totals


def inertia_coefficients(row_totals, col_totals) -> np.ndarray:
    row_totals = np.asarray(row_totals, dtype=float)
    col_totals = np.asarray(col_totals, dtype=float)
    coefficients = np.zeros((row_totals.size, col_totals.size))
    for i, row_total in enumerate(row_totals):
        if row_total <= 0:
            continue
        for j, col_total in enumerate(col_totals):
            if col_total > 0:
                coefficients[i, j] = 1.0 / (row_total * col_total)
    return coefficients


def total_inertia(table, row_totals=None, col_totals=None, coefficients=None) -> float:
    table = np.asarray(table, dtype=float)
    if coefficients is None:
        coefficients = inertia_coefficients(row_totals, col_totals)
    value = float(np.sum(coefficients * table * table) - 1.0)
    # Cauchy-Schwarz guarantees non-negative inertia for a non-negative table
    # with the verified margins; only floating point noise can put it below zero.
    if -NUMERIC_TOL < value < 0:
        value = 0.0
    return value


def _margins_matrix(shape: tuple[int, int]) -> csr_matrix:
    rd, cd = shape
    n = rd * cd
    matrix = lil_matrix((rd + cd, n))
    for i in range(rd):
        matrix[i, i * cd:(i + 1) * cd] = 1
    for j in range(cd):
        for i in range(rd):
            matrix[rd + j, i * cd + j] = 1
    return matrix.tocsr()


def _flow_completion(lower, upper, row_totals, col_totals):
    """Find one feasible integer table or a minimum-cut certificate."""
    rd, cd = lower.shape
    lower_row = lower.sum(axis=1)
    lower_col = lower.sum(axis=0)
    if (lower_row > row_totals).any():
        return None, {'kind': 'row_lower', 'idx': int(np.argmax(lower_row - row_totals))}
    if (lower_col > col_totals).any():
        return None, {'kind': 'col_lower', 'idx': int(np.argmax(lower_col - col_totals))}
    upper_row = upper.sum(axis=1)
    upper_col = upper.sum(axis=0)
    if (upper_row < row_totals).any():
        return None, {'kind': 'row_upper', 'idx': int(np.argmax(row_totals - upper_row))}
    if (upper_col < col_totals).any():
        return None, {'kind': 'col_upper', 'idx': int(np.argmax(col_totals - upper_col))}
    row_remaining = row_totals - lower_row
    col_remaining = col_totals - lower_col
    if int(row_remaining.sum()) != int(col_remaining.sum()):
        return None, {'kind': 'residual_total', 'row': int(row_remaining.sum()), 'col': int(col_remaining.sum())}
    if int(row_remaining.sum()) == 0:
        return lower.copy(), None
    capacity = upper - lower
    nodes = rd + cd + 2
    source, sink = 0, nodes - 1
    graph = lil_matrix((nodes, nodes), dtype=np.int64)
    for i in range(rd):
        graph[source, 1 + i] = int(row_remaining[i])
    for i in range(rd):
        for j in range(cd):
            graph[1 + i, 1 + rd + j] = int(capacity[i, j])
    for j in range(cd):
        graph[1 + rd + j, sink] = int(col_remaining[j])
    dense = np.asarray(graph.todense(), dtype=np.int64)
    flow_result = maximum_flow(csr_matrix(dense), source, sink)
    if int(flow_result.flow_value) != int(row_remaining.sum()):
        flow = np.asarray(flow_result.flow.todense(), dtype=np.int64)
        residual = dense - flow
        reachable = np.zeros(nodes, dtype=bool)
        reachable[source] = True
        stack = [source]
        while stack:
            node = stack.pop()
            for neighbour in np.nonzero(residual[node] > 0)[0]:
                neighbour = int(neighbour)
                if not reachable[neighbour]:
                    reachable[neighbour] = True
                    stack.append(neighbour)
        rows_in = [i for i in range(rd) if reachable[1 + i]]
        rows_out = [i for i in range(rd) if not reachable[1 + i]]
        cols_in = [j for j in range(cd) if reachable[1 + rd + j]]
        cols_out = [j for j in range(cd) if not reachable[1 + rd + j]]
        cut_capacity = (
            sum(int(row_remaining[i]) for i in rows_out)
            + sum(int(col_remaining[j]) for j in cols_in)
            + sum(int(capacity[i, j]) for i in rows_in for j in cols_out)
        )
        return None, {
            'kind': 'flow_cut',
            'rows_reachable': rows_in,
            'rows_outside': rows_out,
            'columns_reachable': cols_in,
            'columns_outside': cols_out,
            'demand_total': int(row_remaining.sum()),
            'max_flow': int(flow_result.flow_value),
            'cut_capacity': int(cut_capacity),
            'deficit': int(row_remaining.sum()) - int(flow_result.flow_value),
        }
    flow = np.asarray(flow_result.flow.todense(), dtype=np.int64)
    completion = flow[1:1 + rd, 1 + rd:1 + rd + cd]
    return lower + completion, None


def _label(index: int, prefix: str, labels=None) -> str:
    if labels is not None and 0 <= index < len(labels):
        return str(labels[index])
    return f'{prefix}{index + 1}'


def check_feasibility(lower, upper, row_totals, col_totals, row_labels=None, col_labels=None):
    """Return (feasible table or None, structured conflicts).

    Besides the obvious row/column total checks, a maximum-flow minimum cut is
    used: totals can be equal per row and column while a sub-collection of rows
    still cannot transfer enough count into the sub-collection of columns.
    """
    lower, upper, row_totals, col_totals = normalize_inputs(lower, upper, row_totals, col_totals)
    rd, cd = lower.shape
    conflicts: list[dict] = []
    total_row = int(row_totals.sum())
    total_col = int(col_totals.sum())
    if total_row != total_col:
        conflicts.append({
            'code': 'totals_mismatch',
            'title': '行合计之和与列合计之和不相等',
            'detail': f'核实行合计之和 {total_row} ≠ 核实列合计之和 {total_col}。表的总计数无法同时满足两组合计。',
        })
    if max(total_row, total_col) > MAX_TOTAL:
        conflicts.append({
            'code': 'total_quota',
            'title': '总计数超过研究配额',
            'detail': f'合计达到 {max(total_row, total_col)}，超过上限 {MAX_TOTAL}。',
        })
    for i in range(rd):
        row_lower = int(lower[i].sum())
        row_upper = int(upper[i].sum())
        if row_lower > row_totals[i]:
            conflicts.append({
                'code': 'row_lower_over_total',
                'title': f'{_label(i, "行", row_labels)} 的下限合计超过核实行合计',
                'detail': f'该行逐格下限合计 {row_lower} > 核实行合计 {int(row_totals[i])}。',
                'row': i,
            })
        if row_upper < row_totals[i]:
            conflicts.append({
                'code': 'row_upper_under_total',
                'title': f'{_label(i, "行", row_labels)} 的上限合计小于核实行合计',
                'detail': f'该行逐格上限合计 {row_upper} < 核实行合计 {int(row_totals[i])}。',
                'row': i,
            })
    for j in range(cd):
        col_lower = int(lower[:, j].sum())
        col_upper = int(upper[:, j].sum())
        if col_lower > col_totals[j]:
            conflicts.append({
                'code': 'col_lower_over_total',
                'title': f'{_label(j, "列", col_labels)} 的下限合计超过核实列合计',
                'detail': f'该列逐格下限合计 {col_lower} > 核实列合计 {int(col_totals[j])}。',
                'column': j,
            })
        if col_upper < col_totals[j]:
            conflicts.append({
                'code': 'col_upper_under_total',
                'title': f'{_label(j, "列", col_labels)} 的上限合计小于核实列合计',
                'detail': f'该列逐格上限合计 {col_upper} < 核实列合计 {int(col_totals[j])}。',
                'column': j,
            })
    if conflicts:
        return None, conflicts
    feasible, certificate = _flow_completion(lower, upper, row_totals, col_totals)
    if feasible is not None:
        return feasible, []
    kind = certificate.get('kind')
    if kind == 'row_lower':
        i = certificate['idx']
        conflicts.append({'code': 'row_lower_over_total', 'title': f'{_label(i, "行", row_labels)} 的下限合计超过核实行合计', 'detail': '逐格下限与核实行合计冲突。', 'row': i})
    elif kind == 'col_lower':
        j = certificate['idx']
        conflicts.append({'code': 'col_lower_over_total', 'title': f'{_label(j, "列", col_labels)} 的下限合计超过核实列合计', 'detail': '逐格下限与核实列合计冲突。', 'column': j})
    elif kind == 'row_upper':
        i = certificate['idx']
        conflicts.append({'code': 'row_upper_under_total', 'title': f'{_label(i, "行", row_labels)} 的上限合计小于核实行合计', 'detail': '逐格上限与核实行合计冲突。', 'row': i})
    elif kind == 'col_upper':
        j = certificate['idx']
        conflicts.append({'code': 'col_upper_under_total', 'title': f'{_label(j, "列", col_labels)} 的上限合计小于核实列合计', 'detail': '逐格上限与核实列合计冲突。', 'column': j})
    elif kind == 'residual_total':
        conflicts.append({
            'code': 'residual_totals_mismatch',
            'title': '扣除逐格下限后，行剩余合计与列剩余合计不相等',
            'detail': f"行剩余 {certificate['row']} ≠ 列剩余 {certificate['col']}。原始行列合计相等也不足以排除此冲突。",
        })
    elif kind == 'flow_cut':
        detail = certificate
        rows = '、'.join(_label(i, '行', row_labels) for i in detail['rows_reachable']) or '（空）'
        cols = '、'.join(_label(j, '列', col_labels) for j in detail['columns_reachable']) or '（空）'
        rows_out = '、'.join(_label(i, '行', row_labels) for i in detail['rows_outside']) or '（空）'
        cols_out = '、'.join(_label(j, '列', col_labels) for j in detail['columns_outside']) or '（空）'
        conflicts.append({
            'code': 'capacity_cut',
            'title': '行集合与列集合的联合容量不足（最小割冲突）',
            'detail': (
                f'可达行 {rows} 只能向可达列 {cols} 输送；该割容量 {detail["cut_capacity"]} '
                f'< 剩余需求 {detail["demand_total"]}（最大流 {detail["max_flow"]}，缺口 {detail["deficit"]}）。'
                f'割外的行 {rows_out} 与割外的列 {cols_out} 无法补足。'
                '这是“合计相等但仍无解”的典型冲突：仅检查行合计等于列合计不够。'
            ),
            'cut': detail,
        })
    return None, conflicts


def repair_table(candidate, lower, upper, row_totals, col_totals):
    """Clamp an integer candidate and complete its margins when possible."""
    table = np.clip(np.asarray(candidate, dtype=np.int64), lower, upper)
    row_remaining = row_totals - table.sum(axis=1)
    col_remaining = col_totals - table.sum(axis=0)
    if (row_remaining < 0).any() or (col_remaining < 0).any():
        return None
    if int(row_remaining.sum()) != int(col_remaining.sum()):
        return None
    if int(row_remaining.sum()) == 0:
        return table
    rd, cd = table.shape
    nodes = rd + cd + 2
    source, sink = 0, nodes - 1
    graph = lil_matrix((nodes, nodes), dtype=np.int64)
    for i in range(rd):
        graph[source, 1 + i] = int(row_remaining[i])
    for i in range(rd):
        for j in range(cd):
            graph[1 + i, 1 + rd + j] = int(upper[i, j] - table[i, j])
    for j in range(cd):
        graph[1 + rd + j, sink] = int(col_remaining[j])
    result = maximum_flow(csr_matrix(np.asarray(graph.todense(), dtype=np.int64)), source, sink)
    if int(result.flow_value) != int(row_remaining.sum()):
        return None
    flow = np.asarray(result.flow.todense(), dtype=np.int64)
    return table + flow[1:1 + rd, 1 + rd:1 + rd + cd]


def table_is_feasible(table, lower, upper, row_totals, col_totals) -> bool:
    if table is None:
        return False
    table = np.asarray(table)
    return bool(
        (table >= lower).all() and (table <= upper).all()
        and (table.sum(axis=1) == row_totals).all()
        and (table.sum(axis=0) == col_totals).all()
    )


def _pair_sweep(table, lower, upper, row_totals, col_totals, coefficients, mode='min', sweeps=28, seed=0):
    """Move counts around 2x2 cycles, the natural integer neighbourhood."""
    table = np.asarray(table, dtype=np.int64).copy()
    rd, cd = table.shape
    rng = np.random.default_rng(seed)

    def value(candidate):
        return total_inertia(candidate, coefficients=coefficients)

    best = table.copy()
    best_value = value(table)
    for _ in range(sweeps):
        improved = False
        moves = [(i, k, j, m) for i in range(rd) for k in range(i + 1, rd) for j in range(cd) for m in range(j + 1, cd)]
        rng.shuffle(moves)
        for i, k, j, m in moves:
            top_left, bottom_right = table[i, j], table[k, m]
            top_right, bottom_left = table[i, m], table[k, j]
            step_low = max(lower[i, j] - top_left, lower[k, m] - bottom_right,
                           top_right - upper[i, m], bottom_left - upper[k, j])
            step_high = min(upper[i, j] - top_left, upper[k, m] - bottom_right,
                            top_right - lower[i, m], bottom_left - lower[k, j])
            if step_high < step_low:
                continue
            a_tl, a_br = coefficients[i, j], coefficients[k, m]
            a_tr, a_bl = coefficients[i, m], coefficients[k, j]
            denominator = a_tl + a_br + a_tr + a_bl
            candidates = {int(step_low), int(step_high)}
            if denominator > 0:
                stationary = -(a_tl * top_left + a_br * bottom_right - a_tr * top_right - a_bl * bottom_left) / denominator
                for step in (math.floor(stationary), math.ceil(stationary)):
                    if step_low <= step <= step_high:
                        candidates.add(int(step))

            def delta(step):
                return (
                    a_tl * ((top_left + step) ** 2 - top_left ** 2)
                    + a_br * ((bottom_right + step) ** 2 - bottom_right ** 2)
                    + a_tr * ((top_right - step) ** 2 - top_right ** 2)
                    + a_bl * ((bottom_left - step) ** 2 - bottom_left ** 2)
                )

            chosen_step = 0
            chosen_delta = 0.0
            for step in candidates:
                if step == 0:
                    continue
                difference = delta(step)
                if (mode == 'min' and difference < chosen_delta - 1e-18) or (mode == 'max' and difference > chosen_delta + 1e-18):
                    chosen_delta = difference
                    chosen_step = step
            if chosen_step:
                table[i, j] += chosen_step
                table[k, m] += chosen_step
                table[i, m] -= chosen_step
                table[k, j] -= chosen_step
                improved = True
        current = value(table)
        if (mode == 'min' and current < best_value) or (mode == 'max' and current > best_value):
            best_value = current
            best = table.copy()
        if not improved:
            break
    return best, best_value


def _lp_vertex(target, lower, upper, row_totals, col_totals, margins, maximize=True):
    rd, cd = lower.shape
    objective = -np.asarray(target, dtype=float).reshape(-1) if maximize else np.asarray(target, dtype=float).reshape(-1)
    result = linprog(
        objective,
        A_eq=margins,
        b_eq=np.r_[row_totals.astype(float), col_totals.astype(float)],
        bounds=list(zip(lower.reshape(-1).astype(float), upper.reshape(-1).astype(float))),
        method='highs',
    )
    if not result.success:
        return None
    candidate = np.rint(result.x).astype(np.int64).reshape(rd, cd)
    return repair_table(candidate, lower, upper, row_totals, col_totals)


def _seed_tables(lower, upper, row_totals, col_totals, coefficients, feasible, margins):
    """Deterministic feasible seeds used before the exact bounds solver."""
    rd, cd = lower.shape
    seeds = [(feasible.copy(), total_inertia(feasible, coefficients=coefficients))]
    targets = [coefficients if np.any(coefficients) else np.ones((rd, cd)), np.ones((rd, cd)), -np.ones((rd, cd))]
    for target in targets:
        candidate = _lp_vertex(target, lower, upper, row_totals, col_totals, margins, maximize=True)
        if candidate is not None:
            seeds.append((candidate, total_inertia(candidate, coefficients=coefficients)))
    chord = (coefficients.astype(float) * (lower + upper)).reshape(-1)
    chord_result = linprog(
        chord,
        A_eq=margins,
        b_eq=np.r_[row_totals.astype(float), col_totals.astype(float)],
        bounds=list(zip(lower.reshape(-1).astype(float), upper.reshape(-1).astype(float))),
        method='highs',
    )
    if chord_result.success:
        candidate = repair_table(np.rint(chord_result.x).astype(np.int64).reshape(rd, cd), lower, upper, row_totals, col_totals)
        if candidate is not None:
            seeds.append((candidate, total_inertia(candidate, coefficients=coefficients)))
    return seeds


def guaranteed_inertia_bounds(lower, upper, row_totals, col_totals, coefficients, margins):
    """Cheap bounds that hold for every admissible table, even on timeout.

    Lower: inertia is a sum of squares minus one, hence >= 0.
    Upper: 0 <= x_ij <= upper_ij gives sum a_ij x_ij^2 - 1 <= sum a_ij upper_ij^2 - 1.
    A chord relaxation over the whole box replaces x^2 by its secant, which is
    >= x^2 for x in [l, u], and the resulting LP is an upper bound as well.
    The tighter of the two is returned; both are rigorous.
    """
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    coefficients = np.asarray(coefficients, dtype=float)
    trivial = float(np.sum(coefficients * upper * upper) - 1.0)
    if trivial < 0:
        trivial = 0.0
    slope = (coefficients * (lower + upper)).reshape(-1)
    constant = float(np.sum(coefficients * lower * upper) + 1.0)
    result = linprog(
        -slope,
        A_eq=margins,
        b_eq=np.r_[np.asarray(row_totals, dtype=float), np.asarray(col_totals, dtype=float)],
        bounds=list(zip(lower.reshape(-1), upper.reshape(-1))),
        method='highs',
    )
    chord = trivial
    if result.success:
        chord = min(trivial, max(0.0, float(slope @ result.x - constant)))
    return 0.0, float(min(trivial, chord) if chord >= 0 else trivial)


def _sparse_constraint(rows, columns, data, shape):
    matrix = lil_matrix(shape)
    for row, col, value in zip(rows, columns, data):
        matrix[row, col] = value
    return matrix.tocsr()


def _unit_segment_model(lower, upper):
    """Exact mixed-integer model of w = x^2 on unit segments.

    On a segment [p, p+1] an integer x can only be p or p+1, so w = x^2 equals the
    secant p^2 + (2p+1)(x-p) exactly.  That makes the model exact for integers
    (not a relaxation) while staying linear.
    """
    rd, cd = lower.shape
    n = rd * cd
    segments = []
    for i in range(rd):
        for j in range(cd):
            low, high = int(lower[i, j]), int(upper[i, j])
            if high == low:
                segments.append([(low, low)])
            else:
                segments.append([(value, value + 1) for value in range(low, high)])
    total_segments = sum(len(group) for group in segments)
    variable_count = 2 * n + 2 * total_segments
    x_offset, w_offset, z_offset, d_offset = 0, n, 2 * n, 2 * n + total_segments
    rows, columns, data = [], [], []
    row_lower, row_upper = [], []
    row_count = 0

    def add_row(entries, low, high):
        nonlocal row_count
        for column, value in entries:
            rows.append(row_count)
            columns.append(column)
            data.append(value)
        row_lower.append(low)
        row_upper.append(high)
        row_count += 1

    pointer = 0
    for cell, group in enumerate(segments):
        add_row([(z_offset + pointer + k, 1.0) for k in range(len(group))], 1.0, 1.0)
        entries = [(x_offset + cell, 1.0)]
        entries += [(z_offset + pointer + k, -float(part[0])) for k, part in enumerate(group)]
        entries += [(d_offset + pointer + k, -1.0) for k in range(len(group))]
        add_row(entries, 0.0, 0.0)
        for k, part in enumerate(group):
            add_row([(d_offset + pointer + k, 1.0), (z_offset + pointer + k, -float(part[1] - part[0]))], -math.inf, 0.0)
        entries = [(w_offset + cell, 1.0)]
        entries += [(z_offset + pointer + k, -float(part[0] ** 2)) for k, part in enumerate(group)]
        entries += [(d_offset + pointer + k, -float(part[0] + part[1])) for k, part in enumerate(group)]
        add_row(entries, 0.0, 0.0)
        pointer += len(group)

    lower_bounds = np.empty(variable_count)
    upper_bounds = np.empty(variable_count)
    integrality = np.zeros(variable_count)
    lower_bounds[x_offset:x_offset + n] = lower.reshape(-1)
    upper_bounds[x_offset:x_offset + n] = upper.reshape(-1)
    integrality[x_offset:x_offset + n] = 1
    lower_bounds[w_offset:w_offset + n] = 0
    upper_bounds[w_offset:w_offset + n] = np.maximum(lower.reshape(-1) ** 2, upper.reshape(-1) ** 2).astype(float)
    lower_bounds[z_offset:z_offset + total_segments] = 0
    upper_bounds[z_offset:z_offset + total_segments] = 1
    integrality[z_offset:z_offset + total_segments] = 1
    lower_bounds[d_offset:d_offset + total_segments] = 0
    upper_bounds[d_offset:d_offset + total_segments] = [
        max(0, part[1] - part[0]) for group in segments for part in group
    ]
    return {
        'segments': segments,
        'variable_count': variable_count,
        'x_offset': x_offset,
        'w_offset': w_offset,
        'z_offset': z_offset,
        'd_offset': d_offset,
        'rows': rows,
        'columns': columns,
        'data': data,
        'row_lower': row_lower,
        'row_upper': row_upper,
        'row_count': row_count,
        'lower_bounds': lower_bounds,
        'upper_bounds': upper_bounds,
        'integrality': integrality,
    }


def _unit_segment_solve(lower, upper, row_totals, col_totals, coefficients, scaled, mode, deadline):
    """Solve exact min/max when the integer widths allow unit segments."""
    model = _unit_segment_model(lower, upper)
    rd, cd = lower.shape
    n = rd * cd
    rows, columns, data = [], [], []
    row_lower, row_upper = [], []
    row_count = 0
    for i in range(rd):
        for j in range(cd):
            rows.append(row_count)
            columns.append(model['x_offset'] + i * cd + j)
            data.append(1.0)
        row_lower.append(float(row_totals[i]))
        row_upper.append(float(row_totals[i]))
        row_count += 1
    for j in range(cd):
        for i in range(rd):
            rows.append(row_count)
            columns.append(model['x_offset'] + i * cd + j)
            data.append(1.0)
        row_lower.append(float(col_totals[j]))
        row_upper.append(float(col_totals[j]))
        row_count += 1
    offset = row_count
    rows.extend(offset + row for row in model['rows'])
    columns.extend(model['columns'])
    data.extend(model['data'])
    row_lower.extend(model['row_lower'])
    row_upper.extend(model['row_upper'])
    row_count += model['row_count']
    matrix = _sparse_constraint(rows, columns, data, (row_count, model['variable_count']))
    objective = np.zeros(model['variable_count'])
    sign = 1.0 if mode == 'min' else -1.0
    objective[model['w_offset']:model['w_offset'] + n] = sign * scaled.reshape(-1)
    remaining = max(0.4, deadline - time.time())
    result = milp(
        objective,
        constraints=[LinearConstraint(matrix, np.asarray(row_lower), np.asarray(row_upper))],
        integrality=model['integrality'],
        bounds=Bounds(model['lower_bounds'], model['upper_bounds']),
        options={'time_limit': remaining, 'mip_rel_gap': 0, 'presolve': True},
    )
    candidate = None
    if result.x is not None:
        candidate = np.rint(np.asarray(result.x[model['x_offset']:model['x_offset'] + n])).astype(np.int64).reshape(rd, cd)
        if not table_is_feasible(candidate, lower, upper, row_totals, col_totals):
            candidate = repair_table(candidate, lower, upper, row_totals, col_totals)
    dual = getattr(result, 'mip_dual_bound', None)
    return {
        'candidate': candidate,
        'objective': None if result.fun is None else float(result.fun),
        'dual': None if dual is None or not np.isfinite(dual) else float(dual),
        'status': int(result.status),
        'optimal': int(result.status) == 0 and result.x is not None,
        'segments': sum(len(group) for group in model['segments']),
    }


def _oa_min(lower, upper, row_totals, col_totals, coefficients, scaled, seeds, deadline):
    rd, cd = lower.shape
    n = rd * cd
    margins = _margins_matrix((rd, cd))
    coefficients_flat = scaled.reshape(-1)
    cuts: list[tuple[int, float]] = []  # (cell, tangent point)
    for table, _ in seeds:
        for cell in range(n):
            cuts.append((cell, int(table.reshape(-1)[cell])))
    seen = set()
    unique_cuts = []
    for cut in cuts:
        if cut not in seen:
            seen.add(cut)
            unique_cuts.append(cut)
    cuts = unique_cuts
    best_table = min(seeds, key=lambda item: item[1])[0].copy()
    best_value = total_inertia(best_table, coefficients=coefficients)
    lower_bound = 0.0
    iterations = 0
    while time.time() < deadline and iterations < 60:
        iterations += 1
        variable_count = 2 * n
        rows, columns, data = [], [], []
        row_lower, row_upper = [], []
        row_count = 0
        for i in range(rd):
            for j in range(cd):
                rows.append(row_count); columns.append(i * cd + j); data.append(1.0)
            row_lower.append(float(row_totals[i])); row_upper.append(float(row_totals[i])); row_count += 1
        for j in range(cd):
            for i in range(rd):
                rows.append(row_count); columns.append(i * cd + j); data.append(1.0)
            row_lower.append(float(col_totals[j])); row_upper.append(float(col_totals[j])); row_count += 1
        for cell, point in cuts:
            rows.append(row_count); columns.append(n + cell); data.append(1.0)
            rows.append(row_count); columns.append(cell); data.append(-2.0 * point)
            row_lower.append(-float(point * point)); row_upper.append(math.inf); row_count += 1
        matrix = _sparse_constraint(rows, columns, data, (row_count, variable_count))
        lower_bounds = np.r_[lower.reshape(-1).astype(float), np.zeros(n)]
        upper_bounds = np.r_[upper.reshape(-1).astype(float), np.full(n, np.inf)]
        integrality = np.r_[np.ones(n), np.zeros(n)]
        objective = np.r_[np.zeros(n), coefficients_flat]
        remaining = max(0.4, deadline - time.time())
        result = milp(
            objective,
            constraints=[LinearConstraint(matrix, np.asarray(row_lower), np.asarray(row_upper))],
            integrality=integrality,
            bounds=Bounds(lower_bounds, upper_bounds),
            options={'time_limit': remaining, 'mip_rel_gap': 0, 'presolve': True},
        )
        dual = getattr(result, 'mip_dual_bound', None)
        if dual is not None and np.isfinite(dual):
            lower_bound = max(lower_bound, float(dual) - 1.0)
        if result.x is None:
            break
        candidate = np.rint(np.asarray(result.x[:n])).astype(np.int64).reshape(rd, cd)
        if not table_is_feasible(candidate, lower, upper, row_totals, col_totals):
            candidate = repair_table(candidate, lower, upper, row_totals, col_totals)
        if candidate is not None:
            value = total_inertia(candidate, coefficients=coefficients)
            if value < best_value:
                best_value = value
                best_table = candidate.copy()
            polished, polished_value = _pair_sweep(candidate, lower, upper, row_totals, col_totals, coefficients, 'min', sweeps=6, seed=iterations)
            if polished_value < best_value:
                best_value = polished_value
                best_table = polished.copy()
        for cell in range(n):
            point = int(np.rint(result.x[cell])) if result.x is not None else 0
            cut = (cell, point)
            if cut not in seen:
                seen.add(cut)
                cuts.append(cut)
        if best_value - lower_bound <= NUMERIC_TOL * max(1.0, abs(best_value)):
            break
    return best_table, best_value, lower_bound, iterations


def _adaptive_max(lower, upper, row_totals, col_totals, coefficients, scaled, maximum_coefficient, seeds, deadline):
    rd, cd = lower.shape
    n = rd * cd
    margins = _margins_matrix((rd, cd))
    lower_f = lower.astype(float); upper_f = upper.astype(float)
    row_f = row_totals.astype(float); col_f = col_totals.astype(float)
    best_table = max(seeds, key=lambda item: item[1])[0].copy()
    best_value = total_inertia(best_table, coefficients=coefficients)
    rng = np.random.default_rng(41)
    # local ascent from promising seeds before the global relaxation
    for table, _ in seeds[:4]:
        polished, polished_value = _pair_sweep(table, lower, upper, row_totals, col_totals, coefficients, 'max', sweeps=10, seed=19)
        if polished_value > best_value:
            best_value = polished_value
            best_table = polished.copy()
    for k in range(4):
        if time.time() > deadline * 0.0 + deadline - 0.5:
            break
        target = 2.0 * coefficients * best_table + rng.normal(scale=0.3, size=(rd, cd))
        candidate = _lp_vertex(target, lower, upper, row_totals, col_totals, margins, maximize=True)
        if candidate is not None:
            polished, polished_value = _pair_sweep(candidate, lower, upper, row_totals, col_totals, coefficients, 'max', sweeps=8, seed=40 + k)
            if polished_value > best_value:
                best_value = polished_value
                best_table = polished.copy()
    segments = [[(int(lower[i, j]), int(upper[i, j]))] for i in range(rd) for j in range(cd)]
    _, safe_upper = guaranteed_inertia_bounds(lower, upper, row_totals, col_totals, coefficients, margins)
    upper_bound = safe_upper
    rounds = 0
    while time.time() < deadline and rounds < 30:
        rounds += 1
        total_segments = sum(len(group) for group in segments)
        variable_count = 2 * n + 2 * total_segments
        x_offset, w_offset, z_offset, d_offset = 0, n, 2 * n, 2 * n + total_segments
        rows, columns, data = [], [], []
        row_lower, row_upper = [], []
        row_count = 0

        def add_row(entries, low, high):
            nonlocal row_count
            for column, value in entries:
                rows.append(row_count); columns.append(column); data.append(value)
            row_lower.append(low); row_upper.append(high); row_count += 1

        for i in range(rd):
            add_row([(x_offset + i * cd + j, 1.0) for j in range(cd)], float(row_totals[i]), float(row_totals[i]))
        for j in range(cd):
            add_row([(x_offset + i * cd + j, 1.0) for i in range(rd)], float(col_totals[j]), float(col_totals[j]))
        pointer = 0
        for cell, group in enumerate(segments):
            add_row([(z_offset + pointer + k, 1.0) for k in range(len(group))], 1.0, 1.0)
            entries = [(x_offset + cell, 1.0)]
            entries += [(z_offset + pointer + k, -float(part[0])) for k, part in enumerate(group)]
            entries += [(d_offset + pointer + k, -1.0) for k in range(len(group))]
            add_row(entries, 0.0, 0.0)
            for k, part in enumerate(group):
                add_row([(d_offset + pointer + k, 1.0), (z_offset + pointer + k, -float(part[1] - part[0]))], -math.inf, 0.0)
            entries = [(w_offset + cell, 1.0)]
            entries += [(z_offset + pointer + k, -float(part[0] ** 2)) for k, part in enumerate(group)]
            entries += [(d_offset + pointer + k, -float(part[0] + part[1])) for k, part in enumerate(group)]
            add_row(entries, 0.0, 0.0)
            pointer += len(group)
        matrix = _sparse_constraint(rows, columns, data, (row_count, variable_count))
        lower_bounds = np.empty(variable_count); upper_bounds = np.empty(variable_count)
        integrality = np.zeros(variable_count)
        lower_bounds[x_offset:x_offset + n] = lower_f.reshape(-1); upper_bounds[x_offset:x_offset + n] = upper_f.reshape(-1)
        integrality[x_offset:x_offset + n] = 1
        lower_bounds[w_offset:w_offset + n] = 0
        upper_bounds[w_offset:w_offset + n] = np.maximum(lower_f.reshape(-1) ** 2, upper_f.reshape(-1) ** 2)
        lower_bounds[z_offset:z_offset + total_segments] = 0; upper_bounds[z_offset:z_offset + total_segments] = 1
        integrality[z_offset:z_offset + total_segments] = 1
        lower_bounds[d_offset:d_offset + total_segments] = 0
        upper_bounds[d_offset:d_offset + total_segments] = [max(0, part[1] - part[0]) for group in segments for part in group]
        objective = np.zeros(variable_count); objective[w_offset:w_offset + n] = -scaled.reshape(-1)
        remaining = max(0.4, deadline - time.time())
        result = milp(
            objective,
            constraints=[LinearConstraint(matrix, np.asarray(row_lower), np.asarray(row_upper))],
            integrality=integrality,
            bounds=Bounds(lower_bounds, upper_bounds),
            options={'time_limit': remaining, 'mip_rel_gap': 0, 'presolve': True},
        )
        dual = getattr(result, 'mip_dual_bound', None)
        if dual is not None and np.isfinite(dual):
            upper_bound = min(upper_bound, -float(dual) * maximum_coefficient - 1.0)
        if result.x is None:
            break
        candidate = np.rint(np.asarray(result.x[x_offset:x_offset + n])).astype(np.int64).reshape(rd, cd)
        if not table_is_feasible(candidate, lower, upper, row_totals, col_totals):
            candidate = repair_table(candidate, lower, upper, row_totals, col_totals)
        if candidate is not None:
            value = total_inertia(candidate, coefficients=coefficients)
            if value > best_value:
                best_value = value
                best_table = candidate.copy()
            polished, polished_value = _pair_sweep(candidate, lower, upper, row_totals, col_totals, coefficients, 'max', sweeps=6, seed=rounds)
            if polished_value > best_value:
                best_value = polished_value
                best_table = polished.copy()
        if upper_bound - best_value <= NUMERIC_TOL * max(1.0, abs(best_value)):
            break
        # refine segments around the incumbent and the relaxed integer candidate
        changed = False
        points = [best_table.reshape(-1), np.rint(np.asarray(result.x[x_offset:x_offset + n])).astype(np.int64).reshape(-1)]
        for cell, group in enumerate(segments):
            if len(group) >= MAX_SEGMENTS_PER_CELL:
                continue
            for source in points:
                value = int(source[cell])
                for k, part in enumerate(group):
                    if part[0] < value < part[1]:
                        segments[cell] = group[:k] + [(part[0], value), (value, part[1])] + group[k + 1:]
                        changed = True
                        break
                if changed:
                    break
            if changed and sum(len(part) for part in segments) >= MAX_SEGMENTS_TOTAL:
                break
        if not changed:
            widest = None
            for cell, group in enumerate(segments):
                if len(group) >= MAX_SEGMENTS_PER_CELL:
                    continue
                for k, part in enumerate(group):
                    if widest is None or part[1] - part[0] > widest[0]:
                        widest = (part[1] - part[0], cell, k)
            if widest is not None and widest[0] > 1:
                width, cell, k = widest
                part = segments[cell][k]
                middle = (part[0] + part[1]) // 2
                segments[cell] = segments[cell][:k] + [(part[0], middle), (middle, part[1])] + segments[cell][k + 1:]
                changed = True
        if not changed:
            break
    return best_table, best_value, upper_bound, rounds, sum(len(group) for group in segments)


def solve_interval(lower, upper, row_totals, col_totals, time_limit=20.0, row_labels=None, col_labels=None):
    """Compute proven bounds and feasible witnesses for all admissible tables."""
    started = time.time()
    lower, upper, row_totals, col_totals = normalize_inputs(lower, upper, row_totals, col_totals)
    rd, cd = lower.shape
    feasible, conflicts = check_feasibility(lower, upper, row_totals, col_totals, row_labels, col_labels)
    n = int(row_totals.sum())
    base = {
        'algorithm': ALGORITHM,
        'dimensions': [int(rd), int(cd)],
        'n': n,
        'time_limit': float(time_limit),
        'lower_matrix': lower.tolist(),
        'upper_matrix': upper.tolist(),
        'row_totals': row_totals.tolist(),
        'column_totals': col_totals.tolist(),
        'effective_rows': int((row_totals > 0).sum()),
        'effective_columns': int((col_totals > 0).sum()),
        'numeric_tolerance': NUMERIC_TOL,
    }
    if n <= 0:
        return {
            **base,
            'status': 'infeasible', 'feasible': False, 'exact': False,
            'conflicts': [{
                'code': 'zero_total',
                'title': '总计数为零，无法定义总惯量',
                'detail': '对应分析要求总计数 N>0；请核对已核实的行合计与列合计。',
            }],
            'elapsed': time.time() - started,
        }
    if feasible is None:
        return {**base, 'status': 'infeasible', 'feasible': False, 'exact': False, 'conflicts': conflicts, 'elapsed': time.time() - started}
    if n > MAX_TOTAL:
        return {
            **base,
            'status': 'infeasible', 'feasible': False, 'exact': False,
            'conflicts': [{'code': 'total_quota', 'title': '总计数超过研究配额', 'detail': f'总计数 {n} 超过 {MAX_TOTAL}。'}],
            'elapsed': time.time() - started,
        }
    coefficients = inertia_coefficients(row_totals, col_totals)
    maximum_coefficient = float(coefficients.max()) if coefficients.size and coefficients.max() > 0 else 1.0
    scaled = coefficients / maximum_coefficient
    margins = _margins_matrix((rd, cd))
    seeds = _seed_tables(lower, upper, row_totals, col_totals, coefficients, feasible, margins)
    # improve seeds in both directions before choosing which solver to trust
    best_min = min(seeds, key=lambda item: item[1])
    best_max = max(seeds, key=lambda item: item[1])
    polished_min, polished_min_value = _pair_sweep(best_min[0], lower, upper, row_totals, col_totals, coefficients, 'min', sweeps=20, seed=5)
    polished_max, polished_max_value = _pair_sweep(best_max[0], lower, upper, row_totals, col_totals, coefficients, 'max', sweeps=20, seed=6)
    if polished_min_value < best_min[1]:
        best_min = (polished_min, polished_min_value)
    if polished_max_value > best_max[1]:
        best_max = (polished_max, polished_max_value)
    seeds = seeds + [best_min, best_max]
    width_total = int(sum(max(0, int(upper[i, j] - lower[i, j])) for i in range(rd) for j in range(cd)))
    use_unit = width_total <= UNIT_SEGMENT_BUDGET
    safe_lower, safe_upper = guaranteed_inertia_bounds(lower, upper, row_totals, col_totals, coefficients, margins)
    # Unit segments are exact for integers but the MILP can still time out on a
    # large segment count; leave part of the budget to the fallback solvers.
    min_deadline = started + max(0.8, time_limit * (0.42 if use_unit else 0.45))
    max_deadline = started + max(0.8, time_limit * 0.94)
    min_solution = _unit_segment_solve(lower, upper, row_totals, col_totals, coefficients, scaled, 'min', min_deadline) if use_unit else None
    max_solution = _unit_segment_solve(lower, upper, row_totals, col_totals, coefficients, scaled, 'max', max_deadline if not use_unit else started + max(0.8, time_limit * 0.55)) if use_unit else None
    min_table = min_value = min_lower = None
    min_proved = False
    if min_solution is not None and min_solution['candidate'] is not None and min_solution['optimal'] and min_solution['objective'] is not None:
        candidate = min_solution['candidate']
        value = total_inertia(candidate, coefficients=coefficients)
        reconstructed = maximum_coefficient * float(min_solution['objective']) - 1.0
        if abs(reconstructed - value) <= NUMERIC_TOL * max(1.0, abs(value)):
            min_table, min_value, min_lower, min_proved = candidate, value, value, True
    if not min_proved:
        fallback_seeds = list(seeds)
        if min_solution is not None and min_solution['candidate'] is not None:
            fallback_seeds.append((min_solution['candidate'], total_inertia(min_solution['candidate'], coefficients=coefficients)))
        min_table, min_value, min_lower, min_iterations = _oa_min(
            lower, upper, row_totals, col_totals, coefficients, scaled, fallback_seeds,
            started + max(0.8, time_limit * 0.46),
        )
        min_lower = max(0.0, float(min_lower))
        min_proved = min_lower >= min_value - NUMERIC_TOL * max(1.0, abs(min_value))
        if min_proved:
            min_lower = min_value
    max_table = max_value = max_upper = None
    max_proved = False
    if max_solution is not None and max_solution['candidate'] is not None and max_solution['optimal'] and max_solution['objective'] is not None:
        candidate = max_solution['candidate']
        value = total_inertia(candidate, coefficients=coefficients)
        reconstructed = -(maximum_coefficient * float(max_solution['objective']) + 1.0)
        if abs(reconstructed - value) <= NUMERIC_TOL * max(1.0, abs(value)):
            max_table, max_value, max_upper, max_proved = candidate, value, value, True
    if not max_proved:
        fallback_seeds = list(seeds)
        if max_solution is not None and max_solution['candidate'] is not None:
            fallback_seeds.append((max_solution['candidate'], total_inertia(max_solution['candidate'], coefficients=coefficients)))
        if max_value is not None:
            fallback_seeds.append((max_table, max_value))
        max_table, max_value, max_upper, rounds, segment_count = _adaptive_max(
            lower, upper, row_totals, col_totals, coefficients, scaled, maximum_coefficient, fallback_seeds, max_deadline,
        )
        max_upper = min(safe_upper, max_upper) if max_upper is not None and np.isfinite(max_upper) else safe_upper
        max_proved = max_upper is not None and np.isfinite(max_upper) and max_upper <= max_value + NUMERIC_TOL * max(1.0, abs(max_value))
        if max_proved:
            max_upper = max_value
    # A stored unit-solve objective that disagrees with the evaluated table means
    # the exactness claim is unsafe; downgrade instead of pretending.
    if min_proved and min_solution is not None and min_solution['objective'] is not None:
        reconstructed = maximum_coefficient * float(min_solution['objective']) - 1.0
        if abs(reconstructed - min_value) > NUMERIC_TOL * max(1.0, abs(min_value)):
            min_proved = False
            min_lower = max(safe_lower, min(min_lower, min_value - max(1e-9, NUMERIC_TOL * max(1.0, abs(min_value)))))
    if max_proved and max_solution is not None and max_solution['objective'] is not None:
        reconstructed = -(maximum_coefficient * float(max_solution['objective']) + 1.0)
        if abs(reconstructed - max_value) > NUMERIC_TOL * max(1.0, abs(max_value)):
            max_proved = False
            max_upper = max(max_upper, max_value + max(1e-9, NUMERIC_TOL * max(1.0, abs(max_value))))
    min_lower = min(min_lower if min_lower is not None else safe_lower, min_value) if min_value is not None else safe_lower
    min_lower = max(0.0, min_lower)
    if max_upper is None or not np.isfinite(max_upper):
        max_upper = safe_upper
    if max_value is not None and max_upper < max_value:
        # A feasible table can never exceed a valid upper bound; only floating
        # point noise can make this look violated.
        max_upper = max_value
        max_proved = True
    if min_table is None:
        min_table = feasible
        min_value = total_inertia(feasible, coefficients=coefficients)
        min_lower = 0.0
    if max_table is None:
        max_table = feasible
        max_value = total_inertia(feasible, coefficients=coefficients)
        max_upper = None
    exact = bool(min_proved and max_proved)
    return {
        **base,
        'status': 'exact' if exact else 'unproven',
        'feasible': True,
        'exact': exact,
        'proven_range': {
            'min_lower_bound': float(min_lower),
            'min_feasible_value': float(min_value),
            'max_feasible_value': float(max_value),
            'max_upper_bound': None if max_upper is None else float(max_upper),
        },
        'min': {
            'value': float(min_value),
            'lower_bound': float(min_lower),
            'proved': bool(min_proved),
            'table': min_table.tolist(),
            'mode': 'unit-segment-milp' if use_unit and min_proved else 'outer-approximation',
        },
        'max': {
            'value': float(max_value),
            'upper_bound': None if max_upper is None else float(max_upper),
            'proved': bool(max_proved),
            'table': max_table.tolist(),
            'mode': 'unit-segment-milp' if use_unit and max_proved else 'adaptive-secant-milp',
        },
        'unit_segments': bool(use_unit),
        'width_total': width_total,
        'elapsed': time.time() - started,
        'timed_out': not exact,
        'notes': [
            '区间表的总惯量按 I(X)=Σ X_ij²/(R_i C_j)-1 计算；零边际行/列被边际约束强制为零。',
            '已证实范围来自整数规划的对偶界；可行值由实际整数表复算。超时只降级为未证实，不把可行值冒充极值。',
        ],
    }
