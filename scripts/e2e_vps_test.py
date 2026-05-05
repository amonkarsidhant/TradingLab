#!/usr/bin/env python3
"""End-to-end test — Sid Trading Lab on VPS (Phase 2+3)."""
import sys, traceback
passed = failed = 0

def test(name):
    def decorator(fn):
        global passed, failed
        print(f"\n{'='*50}\nTEST: {name}\n{'='*50}")
        try:
            fn()
            print("  ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
            traceback.print_exc()
            failed += 1
        return fn
    return decorator

# ── Phase 2 ────────────────────────────────────────────────────────────────

@test("Phase 2: Sandbox real strategy (simple_momentum)")
def t_sbox_real():
    from pathlib import Path
    from trading_lab.meta.sandbox import SyntaxSandbox
    src = Path("/home/sidhant/TradingLab/src/trading_lab/strategies/simple_momentum.py").read_text()
    r = SyntaxSandbox.validate(src)
    assert r.valid, f"valid={r.valid}"
    assert r.has_generate_signal
    print(f"  valid={r.valid}, has_gs={r.has_generate_signal}")

@test("Phase 2: Sandbox fake variant")
def t_sbox_fake():
    from trading_lab.meta.sandbox import SyntaxSandbox
    src = "class T(Strategy):\n    def generate_signal(self,t,p): return Signal(strategy='T',ticker=t,action=SignalAction.BUY)"
    r = SyntaxSandbox.validate(src)
    assert r.has_generate_signal
    print(f"  has_gs={r.has_generate_signal}")

@test("Phase 2: Sandbox malicious code")
def t_sbox_bad():
    from trading_lab.meta.sandbox import SyntaxSandbox
    src = "import os; os.system('rm -rf /')"
    r = SyntaxSandbox.validate(src)
    assert not r.valid
    print(f"  valid={r.valid} (correctly rejected)")

@test("Phase 2: ChangeLog")
def t_changelog():
    from trading_lab.meta.change_log import ChangeLog
    cl = ChangeLog()
    cl.record("simple_momentum", "e2e_test", "test", 0.5)
    entries = cl.list_changes(strategy_id="simple_momentum", limit=1)
    print(f"  entries={len(entries)}, latest action={entries[0]['action'] if entries else 'none'}")

@test("Phase 2: AdoptionManager")
def t_adoption():
    from trading_lab.meta.adoption_manager import AdoptionManager
    m = AdoptionManager()
    print(f"  OK")

@test("Phase 2: VariantValidator")
def t_validator():
    from trading_lab.meta.variant_validator import VariantValidator
    v = VariantValidator()
    print("  OK")

# ── Phase 3 ────────────────────────────────────────────────────────────────

@test("Phase 3: FeatureEngine (30 bars)")
def t_features():
    import numpy as np
    from trading_lab.alpha.features import FeatureEngine
    e = FeatureEngine()
    close = np.arange(100.0, 130.0) + np.random.RandomState(42).normal(0, 0.5, 30)
    open_ = close * 0.99
    high = close * 1.01
    low = close * 0.98
    vol = np.ones(30) * 1e6
    fs = e.compute("SPY", open_, high, low, close, vol,
                   feature_names=["rsi_14","momentum_5d","atr_14_pct"])
    assert len(fs.names()) == 3
    print(f"  features={len(fs.names())}")
    for n in fs.names():
        print(f"  {n}={fs.latest(n):.4f}")

@test("Phase 3: NeuralSignalModel")
def t_neural():
    from trading_lab.alpha.neural_signal import NeuralSignalModel
    m = NeuralSignalModel()
    assert m.parameter_count() < 10000
    print(f"  params={m.parameter_count()}")

@test("Phase 3: Simulation")
def t_sim():
    from trading_lab.alpha.simulation import MultiAgentSimulation
    sim = MultiAgentSimulation(lookback_days=30, tickers=["SPY"], include_neural=False)
    results = sim.run()
    assert len(results) > 0
    print(f"  agents={len(results)}")
    for r in results:
        print(f"  {r.agent_id}: eq={r.final_equity:.4f} sharpe={r.sharpe:.2f} trades={r.trades}")

@test("Phase 3: SimulationAnalytics")
def t_sim_analytics():
    from trading_lab.alpha.analytics import SimulationAnalytics
    a = SimulationAnalytics()
    sims = a.list_sims(limit=5)
    print(f"  sims in db={len(sims)}")

@test("Phase 3: Integration")
def t_integration():
    from trading_lab.alpha.integration import AlphaIntegration
    a = AlphaIntegration()
    print("  OK")

# ── CLI ────────────────────────────────────────────────────────────────

@test("CLI: Phase 3 commands --help")
def t_cli_help():
    import subprocess
    cmds = ["discover-alpha","engineer-features","neural-signal","run-simulation","sim-leaderboard"]
    for c in cmds:
        r = subprocess.run([
            "/home/sidhant/TradingLab/.venv/bin/python3","-m","trading_lab.cli",c,"--help"
        ], capture_output=True)
        ok = r.returncode == 0
        print(f"  {c}: {'OK' if ok else 'FAIL'}")
        assert ok, f"{c} --help failed"

# ── Database ───────────────────────────────────────────────────────────

@test("DB: All expected tables")
def t_db_tables():
    import sqlite3
    conn = sqlite3.connect('/home/sidhant/TradingLab/trading_lab.sqlite3')
    t = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = ['signals','cycles','round_trips','ab_results','strategy_change_log','simulations','simulation_agent_results']
    for e in expected:
        assert e in t, f"missing {e}"
        print(f"  {e}: OK")

@test("DB: Cycles have regime")
def t_db_cycles():
    import sqlite3
    c = sqlite3.connect('/home/sidhant/TradingLab/trading_lab.sqlite3').execute(
        'SELECT regime FROM cycles ORDER BY id DESC LIMIT 1').fetchone()
    print(f"  last regime={c[0] if c else 'N/A'}")

# ── Run ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    t_sbox_real(); t_sbox_fake(); t_sbox_bad(); t_changelog(); t_adoption(); t_validator()
    t_features(); t_neural(); t_sim(); t_sim_analytics(); t_integration()
    t_cli_help()
    t_db_tables(); t_db_cycles()
    print(f"\n{'='*50}\nTOTAL: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
