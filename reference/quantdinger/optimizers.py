"""Iterative parameter-space optimizers for the experiment pipeline.

Two algorithms are exposed:

* ``DifferentialEvolutionOptimizer`` — classic ``rand/1/bin`` DE adapted for
  the discrete index-encoded parameter spaces we already use for grid/random
  search. Each parameter is a list of allowed values; DE works on the index
  vector and rounds back to a value on every materialisation.
* ``TPEOptimizer`` — a lightweight Tree-structured Parzen Estimator that
  approximates ``optuna``-style sampling without pulling in the dependency.
  It splits observed trials into a "good" (top γ%) and "rest" group, then
  samples new candidates from a per-parameter mixture of Gaussians centred on
  good trials (with annealed bandwidth).

Both optimizers share an ``ask`` / ``tell`` contract so the runner can drive
them in the same loop. ``ask`` returns a *batch* of override dicts (so the
caller can batch backtests if useful); ``tell`` accepts the matching list of
``(overrides, score)`` pairs to update internal state.

The optimizers are intentionally **dependency-free** (stdlib only) and
**budget-aware**: they are useful for ~20–80 evaluations, which matches the
realistic backtest budget — anything more is bounded by ``max_evals``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def normalize_space(parameter_space: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Materialise every parameter spec to an explicit list of values.

    Mirrors ``StrategyEvolutionService._resolve_values`` semantics so the
    same ``parameterSpace`` payload works across grid / random / DE / TPE.
    Empty / invalid specs are dropped silently.
    """
    out: Dict[str, List[Any]] = {}
    for path, spec in (parameter_space or {}).items():
        values = _resolve_values(spec)
        if values:
            out[str(path)] = values
    return out


def _resolve_values(spec: Any) -> List[Any]:
    if isinstance(spec, list):
        return list(spec)
    if isinstance(spec, tuple):
        return list(spec)
    if isinstance(spec, dict):
        minimum = spec.get('min')
        maximum = spec.get('max')
        step = spec.get('step', 1)
        if minimum is None or maximum is None:
            return []
        if step == 0:
            return [minimum]
        values: List[Any] = []
        cursor = minimum
        # Inclusive of the maximum modulo float noise — same convention as
        # StrategyEvolutionService._resolve_values.
        while cursor <= maximum + 1e-12:
            values.append(round(cursor, 10) if isinstance(cursor, float) else cursor)
            cursor += step
        return values
    return [spec]


def _index_to_overrides(
    index_vec: List[int],
    keys: List[str],
    values_by_key: Dict[str, List[Any]],
) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for i, key in enumerate(keys):
        vlist = values_by_key[key]
        idx = max(0, min(len(vlist) - 1, int(round(index_vec[i]))))
        overrides[key] = vlist[idx]
    return overrides


def _overrides_to_index(
    overrides: Dict[str, Any],
    keys: List[str],
    values_by_key: Dict[str, List[Any]],
) -> List[int]:
    out: List[int] = []
    for key in keys:
        vlist = values_by_key[key]
        v = overrides.get(key)
        try:
            out.append(vlist.index(v))
        except ValueError:
            out.append(0)
    return out


# ---------------------------------------------------------------------------
# Differential Evolution
# ---------------------------------------------------------------------------


@dataclass
class _DEMember:
    index_vec: List[float]
    overrides: Dict[str, Any]
    score: float = float('-inf')


class DifferentialEvolutionOptimizer:
    """Classic DE (``rand/1/bin``) over index-encoded discrete parameters.

    The population size and generation count are derived from ``max_evals``
    so the optimizer never overruns the user-specified evaluation budget.
    """

    def __init__(
        self,
        parameter_space: Dict[str, Any],
        *,
        max_evals: int = 32,
        population_size: Optional[int] = None,
        f: float = 0.6,
        cr: float = 0.7,
        seed: int = 0xC0DE,
    ) -> None:
        self.values_by_key = normalize_space(parameter_space)
        self.keys = list(self.values_by_key.keys())
        if not self.keys:
            raise ValueError('DE optimizer requires a non-empty parameterSpace')

        self.max_evals = max(8, int(max_evals))
        # Pick a sensible default population: DE typically wants P >= 4 and
        # P × G ≈ max_evals. We bias towards ~3 generations on small budgets.
        if population_size is None:
            population_size = max(4, min(12, self.max_evals // 3))
        self.population_size = int(population_size)
        self.f = float(f)
        self.cr = float(cr)
        self.rng = random.Random(seed)

        self.population: List[_DEMember] = []
        self.evaluations_used = 0
        self._initialised = False
        # Pending evaluations awaiting their score for the next ``tell``.
        self._pending: List[Tuple[int, _DEMember]] = []
        self._mode = 'init'  # 'init' → seed population, 'evolve' → trial vectors

    # ---- public API -------------------------------------------------------

    def ask(self, batch_size: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return the next batch of override dicts to evaluate.

        Returns an empty list once the eval budget is exhausted. The batch
        size defaults to ``population_size`` so the runner can backtest one
        generation at a time.
        """
        if self.evaluations_used >= self.max_evals:
            return []

        batch_size = int(batch_size or self.population_size)
        # Don't propose more than the remaining budget.
        budget_left = self.max_evals - self.evaluations_used
        batch_size = max(1, min(batch_size, budget_left))

        if not self._initialised:
            return self._seed_population(batch_size)
        return self._generate_trials(batch_size)

    def tell(self, results: Iterable[Tuple[Dict[str, Any], float]]) -> None:
        """Feed back scores in the same order as the previous ``ask`` batch."""
        results = list(results)
        if len(results) != len(self._pending):
            # Be forgiving — match by min length. The runner can drop failed
            # backtests silently rather than aborting the whole pipeline.
            n = min(len(results), len(self._pending))
            results = results[:n]
            pending = self._pending[:n]
        else:
            pending = self._pending

        for (target_idx, candidate), (_overrides, score) in zip(pending, results):
            candidate.score = float(score or 0.0)
            self.evaluations_used += 1

            if self._mode == 'init':
                # Seed phase: just place into population slot.
                if 0 <= target_idx < len(self.population):
                    self.population[target_idx] = candidate
                else:
                    self.population.append(candidate)
            else:
                # Evolve phase: greedy selection vs incumbent.
                if 0 <= target_idx < len(self.population):
                    incumbent = self.population[target_idx]
                    if candidate.score >= incumbent.score:
                        self.population[target_idx] = candidate

        self._pending = []

        if self._mode == 'init' and len(self.population) >= self.population_size:
            self._initialised = True
            self._mode = 'evolve'

    def best(self) -> Optional[Dict[str, Any]]:
        if not self.population:
            return None
        best = max(self.population, key=lambda m: m.score)
        return {'overrides': best.overrides, 'score': best.score}

    # ---- internal --------------------------------------------------------

    def _seed_population(self, batch_size: int) -> List[Dict[str, Any]]:
        """Initial Latin-hypercube-style seeding over the index space."""
        needed = self.population_size - len(self.population) - len(self._pending)
        n = max(1, min(batch_size, needed))
        proposals: List[Dict[str, Any]] = []
        for slot in range(n):
            index_vec: List[float] = []
            for key in self.keys:
                hi = len(self.values_by_key[key]) - 1
                index_vec.append(float(self.rng.randint(0, max(0, hi))))
            overrides = _index_to_overrides(
                [int(round(v)) for v in index_vec], self.keys, self.values_by_key,
            )
            member = _DEMember(index_vec=index_vec, overrides=overrides)
            target_idx = len(self.population) + len(self._pending) + slot
            self._pending.append((target_idx, member))
            proposals.append(overrides)
        return proposals

    def _generate_trials(self, batch_size: int) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []
        for slot in range(batch_size):
            target = (self.evaluations_used + slot) % self.population_size
            trial_vec = self._mutate_and_crossover(target)
            overrides = _index_to_overrides(
                [int(round(v)) for v in trial_vec], self.keys, self.values_by_key,
            )
            member = _DEMember(index_vec=trial_vec, overrides=overrides)
            self._pending.append((target, member))
            proposals.append(overrides)
        return proposals

    def _mutate_and_crossover(self, target_idx: int) -> List[float]:
        pop = self.population
        n = len(pop)
        # Pick three distinct donors != target.
        indices = [i for i in range(n) if i != target_idx]
        self.rng.shuffle(indices)
        a, b, c = indices[0], indices[1 % (n - 1) if n > 2 else 0], indices[2 % (n - 1) if n > 3 else 0]
        donor_a = pop[a].index_vec
        donor_b = pop[b].index_vec
        donor_c = pop[c].index_vec
        target = pop[target_idx].index_vec

        mutant = [
            donor_a[i] + self.f * (donor_b[i] - donor_c[i])
            for i in range(len(self.keys))
        ]

        # Binomial crossover.
        trial = list(target)
        j_rand = self.rng.randint(0, len(self.keys) - 1)
        for i in range(len(self.keys)):
            if self.rng.random() < self.cr or i == j_rand:
                trial[i] = mutant[i]

        # Bounce-back on boundary violation so we stay inside the discrete
        # space without wasting an eval on a clamped corner.
        for i, key in enumerate(self.keys):
            hi = len(self.values_by_key[key]) - 1
            if trial[i] < 0:
                trial[i] = -trial[i]
            if trial[i] > hi:
                trial[i] = 2 * hi - trial[i]
            trial[i] = max(0.0, min(float(hi), trial[i]))
        return trial


# ---------------------------------------------------------------------------
# Tree-structured Parzen Estimator (lightweight)
# ---------------------------------------------------------------------------


class TPEOptimizer:
    """Lightweight TPE-like sampler.

    Implementation notes — this is a *simplification* of the canonical Hyperopt
    TPE: rather than fitting full kernel densities, we sample a candidate by
    picking a "good" historical trial uniformly at random and then jittering
    its index for each parameter with annealed Gaussian noise. With more than
    ~16 trials we apply expected-improvement-style filtering: draw 4 candidates
    per slot and pick the one furthest from the "bad" trial cluster centroid.
    This captures TPE's "exploit + diversify" behaviour at a fraction of the
    code (and zero deps).
    """

    def __init__(
        self,
        parameter_space: Dict[str, Any],
        *,
        max_evals: int = 32,
        startup_trials: int = 8,
        gamma: float = 0.25,
        seed: int = 0xC0DE,
    ) -> None:
        self.values_by_key = normalize_space(parameter_space)
        self.keys = list(self.values_by_key.keys())
        if not self.keys:
            raise ValueError('TPE optimizer requires a non-empty parameterSpace')

        self.max_evals = max(8, int(max_evals))
        self.startup_trials = max(4, min(int(startup_trials), self.max_evals // 2 or 4))
        self.gamma = float(gamma)
        self.rng = random.Random(seed)

        self.history: List[Tuple[List[int], Dict[str, Any], float]] = []
        self._pending: List[Tuple[List[int], Dict[str, Any]]] = []
        self.evaluations_used = 0

    # ---- public API ------------------------------------------------------

    def ask(self, batch_size: Optional[int] = None) -> List[Dict[str, Any]]:
        if self.evaluations_used >= self.max_evals:
            return []
        n = int(batch_size or 4)
        budget_left = self.max_evals - self.evaluations_used
        n = max(1, min(n, budget_left))

        proposals: List[Dict[str, Any]] = []
        for _ in range(n):
            if len(self.history) < self.startup_trials:
                idx_vec = self._random_index_vec()
            else:
                idx_vec = self._sample_via_tpe()
            overrides = _index_to_overrides(idx_vec, self.keys, self.values_by_key)
            self._pending.append((idx_vec, overrides))
            proposals.append(overrides)
        return proposals

    def tell(self, results: Iterable[Tuple[Dict[str, Any], float]]) -> None:
        results = list(results)
        n = min(len(results), len(self._pending))
        for i in range(n):
            idx_vec, _overrides = self._pending[i]
            _override, score = results[i]
            self.history.append((idx_vec, _override, float(score or 0.0)))
            self.evaluations_used += 1
        self._pending = self._pending[n:]

    def best(self) -> Optional[Dict[str, Any]]:
        if not self.history:
            return None
        idx_vec, overrides, score = max(self.history, key=lambda h: h[2])
        return {'overrides': overrides, 'score': score}

    # ---- internal --------------------------------------------------------

    def _random_index_vec(self) -> List[int]:
        return [
            self.rng.randint(0, max(0, len(self.values_by_key[key]) - 1))
            for key in self.keys
        ]

    def _sample_via_tpe(self) -> List[int]:
        # Partition history into good vs. rest using the gamma quantile.
        sorted_hist = sorted(self.history, key=lambda h: h[2], reverse=True)
        n_good = max(2, int(math.ceil(len(sorted_hist) * self.gamma)))
        good = sorted_hist[:n_good]
        bad = sorted_hist[n_good:]

        # Annealing bandwidth: starts at ~25% of the parameter range, decays
        # towards ~5% as we accumulate trials.
        progress = min(1.0, self.evaluations_used / max(1, self.max_evals))
        sigma_frac = max(0.05, 0.25 * (1.0 - progress))

        # Draw 4 candidates around random good trials; pick the one with the
        # largest distance from the bad-trial centroid (EI proxy).
        best_idx: Optional[List[int]] = None
        best_distance = -1.0
        for _ in range(4):
            seed_trial = self.rng.choice(good)
            seed_vec = seed_trial[0]
            candidate: List[int] = []
            for i, key in enumerate(self.keys):
                hi = len(self.values_by_key[key]) - 1
                sigma = max(1.0, sigma_frac * hi)
                jitter = self.rng.gauss(0.0, sigma)
                v = int(round(seed_vec[i] + jitter))
                v = max(0, min(hi, v))
                candidate.append(v)
            d = self._mean_distance(candidate, bad) if bad else 0.0
            if d > best_distance:
                best_distance = d
                best_idx = candidate
        return best_idx or self._random_index_vec()

    @staticmethod
    def _mean_distance(
        candidate: List[int],
        trials: List[Tuple[List[int], Dict[str, Any], float]],
    ) -> float:
        if not trials:
            return 0.0
        total = 0.0
        for trial in trials:
            vec = trial[0]
            total += math.sqrt(sum((candidate[i] - vec[i]) ** 2 for i in range(len(vec))))
        return total / len(trials)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_optimizer(
    method: str,
    parameter_space: Dict[str, Any],
    *,
    max_evals: int = 32,
    seed: int = 0xC0DE,
):
    """Construct an optimizer by method name.

    Returns ``None`` for unsupported / non-iterative methods (grid, random) so
    the caller can fall back to the existing one-shot variant builder.
    """
    method = str(method or '').lower()
    if method == 'de':
        return DifferentialEvolutionOptimizer(
            parameter_space, max_evals=max_evals, seed=seed,
        )
    if method == 'tpe':
        return TPEOptimizer(
            parameter_space, max_evals=max_evals, seed=seed,
        )
    return None
