import numpy as np
import pandas as pd

def compute_abs_plasticity(
    file_path,
    time_reset_threshold=0.05,
    force_threshold=0.3,
    min_cycle_length=10
):
    """
    Calcule UNIQUEMENT la plasticité ABSOLUE par cycle:
      Abs_plast_mm = d_return(Fref) - d0(Fref)
    où d0(Fref) est pris sur le 1er cycle (franchissement montant interpolé).
    Retour: DataFrame [Cycle, Abs_plast_mm, Cycle_time_s, Cumulative_time_min]
    """


    data = np.loadtxt(file_path)
    t, d, f = data[:,0], data[:,1], data[:,2]

    # Découpe en cycles via reset du temps
    cuts = [0] + [i for i in range(1, len(t)) if t[i] < t[i-1] - time_reset_threshold] + [len(t)]
    if len(cuts) < 2:
        return pd.DataFrame(columns=["Cycle","Abs_plast_mm","Cycle_time_s","Cumulative_time_min"])

    # Interpolation d0(Fref) sur le cycle 1 (passage montant)
    seg0_f, seg0_d = f[cuts[0]:cuts[1]], d[cuts[0]:cuts[1]]
    above0 = np.where(seg0_f >= force_threshold)[0]
    if above0.size == 0 or above0[0] - 1 < 0:
        # pas de franchissement → pas de calcul possible
        return pd.DataFrame(columns=["Cycle","Abs_plast_mm","Cycle_time_s","Cumulative_time_min"])
    i1, i0 = above0[0], above0[0] - 1
    f0, f1 = seg0_f[i0], seg0_f[i1]
    d0_0, d0_1 = seg0_d[i0], seg0_d[i1]
    if f1 == f0:
        return pd.DataFrame(columns=["Cycle","Abs_plast_mm","Cycle_time_s","Cumulative_time_min"])
    alpha0 = (force_threshold - f0) / (f1 - f0)
    d0 = d0_0 + alpha0 * (d0_1 - d0_0)  # référence absolue

    abs_plast, cycle_times = [], []
    for idx in range(len(cuts)-1):
        s, e = cuts[idx], cuts[idx+1]
        seg_f, seg_d, seg_t = f[s:e], d[s:e], t[s:e]
        if len(seg_f) < min_cycle_length:
            continue

        # 1) franchissement montant (trouve i1)
        above = np.where(seg_f >= force_threshold)[0]
        if above.size == 0 or above[0] - 1 < 0:
            continue
        i1 = above[0]; i0 = i1 - 1
        f0, f1 = seg_f[i0], seg_f[i1]
        d0a, d1a = seg_d[i0], seg_d[i1]
        if f1 == f0:
            continue
        alpha = (force_threshold - f0) / (f1 - f0)
        d_start = d0a + alpha * (d1a - d0a)

        # 2) franchissement descendant (trouve j1)
        below = np.where(seg_f[i1:] <= force_threshold)[0]
        if below.size == 0:
            continue
        j1 = i1 + below[0]
        if j1 - 1 < 0 or j1 >= len(seg_f):
            continue
        j0 = j1 - 1
        f0b, f1b = seg_f[j0], seg_f[j1]
        d0b, d1b = seg_d[j0], seg_d[j1]
        if f1b == f0b:
            continue
        beta = (force_threshold - f0b) / (f1b - f0b)
        d_return = d0b + beta * (d1b - d0b)

        # Plasticité ABSOLUE: décalage par rapport à d0(Fref)
        abs_plast.append(d_return - d0)
        cycle_times.append(seg_t[-1] - seg_t[0])

    cycles = np.arange(1, len(abs_plast) + 1)
    cum_time_min = (np.cumsum(cycle_times)/60.0) if cycle_times else []

    return pd.DataFrame({
        "Cycle": cycles,
        "Abs_plast_mm": abs_plast,
        "Cycle_time_s": cycle_times,
        "Cumulative_time_min": cum_time_min
    })

def plot_cycles_on_axes(ax, cycles, title="Force vs Déplacement par cycle"):
    """
    Trace une liste de DataFrames [time, distance, force] sur l'axe `ax`.
    Ne fait AUCUN plt.show(); idéal pour un embed Qt.
    """
    import matplotlib.pyplot as plt

    ax.clear()
    ax.set_title(title)
    ax.set_xlabel("Déplacement (mm)")
    ax.set_ylabel("Force (N)")
    ax.grid(True)

    if not cycles:
        ax.text(0.5, 0.5, "Aucun cycle chargé", ha="center", va="center")
        return

    # Palette stable selon le nombre de cycles
    cmap = plt.cm.get_cmap("tab10", len(cycles))

    for i, df in enumerate(cycles):
        if df is None or df.empty or not {"distance","force"} <= set(df.columns):
            continue
        ax.plot(df["distance"], df["force"], label=f"Cycle {i}", color=cmap(i))
        # Points (optionnel)
        ax.scatter(df["distance"], df["force"], s=6, alpha=0.8, color=cmap(i))

    # Légende seulement si raisonnable
    if len(cycles) <= 12:
        ax.legend(loc="best")


def compute_global_target_plasticity_interp(file_path: str, F0: float = 0.05) -> float | None:
    """
    Target = d(last crossing at F0) - d(first crossing at F0), using linear interpolation
    on the whole file (not per-cycle). Returns None if we cannot bracket F0 twice.
    """
    data = np.loadtxt(file_path)
    t, d, f = data[:,0], data[:,1], data[:,2]

    s = f - F0
    crossings = np.nonzero(s[:-1] * s[1:] <= 0)[0]  # indices i where [i,i+1] brackets F0
    if crossings.size < 1:
        return None

    def interp_d(i: int) -> float | None:
        f0, f1 = f[i], f[i+1]
        if f1 == f0: return None
        lam = (F0 - f0) / (f1 - f0)
        return float(d[i] + lam * (d[i+1] - d[i]))

    # first crossing
    d_first = interp_d(int(crossings[0]))
    # last crossing (use the last bracket in the series)
    d_last  = interp_d(int(crossings[-1]))
    if d_first is None or d_last is None:
        return None
    return float(d_last - d_first)

def _pava(y: np.ndarray) -> np.ndarray:
    """Isotonic (non-decreasing) regression."""
    y = np.asarray(y, float); n = len(y)
    g = y.copy(); w = np.ones(n)
    i = 0
    while i < n-1:
        if g[i] <= g[i+1] + 1e-12:
            i += 1
        else:
            new = (w[i]*g[i] + w[i+1]*g[i+1])/(w[i]+w[i+1])
            g[i]=g[i+1]=new; w[i]=w[i+1]=w[i]+w[i+1]
            j=i
            while j>0 and g[j-1] > g[j] + 1e-12:
                new=(w[j-1]*g[j-1]+w[j]*g[j])/(w[j-1]+w[j])
                g[j-1]=g[j]=new; w[j-1]=w[j]=w[j-1]+w[j]
                j -= 1
            i = max(j, 0)
    return g

def calibrate_threshold_match_target_first(
    file_path: str,
    target_F0: float = 0.05,          # “a little above 0”
    time_reset_threshold: float = 0.05,
    min_cycle_length: int = 10,
    search_range=(0.01, 1.5),         # allow near-zero if needed to hit target
    step: float = 0.005,
):
    """
    Primary:  |last(isotone(abs_plast)) - TARGET(F0)|   (smaller is better)
    Secondary: total downward drops of the raw curve  (sum of negative diffs)
    Tertiary:  RMSE raw vs isotone (smoother is better)
    Returns: (best_thresh, diagnostics_dict)
    """
    target = compute_global_target_plasticity_interp(file_path, F0=target_F0)
    if target is None:
        return None, {"reason": "no valid near-zero crossings", "target": None}

    best = None
    best_key = (np.inf, np.inf, np.inf)
    diag = {"target": float(target), "candidates": {}}

    thresholds = np.arange(search_range[0], search_range[1] + step, step)
    for ft in thresholds:
        df = compute_abs_plasticity(
            file_path,
            time_reset_threshold=time_reset_threshold,
            force_threshold=float(ft),
            min_cycle_length=min_cycle_length
        )
        if df.empty or "Abs_plast_mm" not in df:
            continue

        y = pd.to_numeric(df["Abs_plast_mm"], errors="coerce").dropna().values
        if y.size < 4:
            continue

        # Monotone projection
        yhat = _pava(y)

        # PRIMARY: closeness to target (use monotone final value)
        abs_err_hat = float(abs(yhat[-1] - target))

        # SECONDARY: total negative drops on raw series
        dif = np.diff(y)
        sum_neg = float(np.sum(np.clip(-dif, 0.0, None)))

        # TERTIARY: smoothness (fit to isotone)
        rmse = float(np.sqrt(np.mean((y - yhat)**2)))

        key = (abs_err_hat, sum_neg, rmse)
        diag["candidates"][float(ft)] = {
            "abs_err_hat": abs_err_hat,
            "sum_neg": sum_neg,
            "rmse": rmse,
            "last_hat": float(yhat[-1]),
            "last_raw": float(y[-1]),
            "n": int(y.size),
        }

        if key < best_key:
            best_key = key
            best = float(ft)

    return best, diag