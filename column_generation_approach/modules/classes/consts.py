# ────────────────────────────────────────────────────────────
#  CONFIGURATION CONSTANTS
# ────────────────────────────────────────────────────────────

# clingcon invocation via uv
CLINGCON_CMD = ["uv", "run", "python", "-m", "clingcon"]

# Column generation parameters
MAX_CG_ITERATIONS    = 50
MAX_PACKINGS_PER_TR  = 10        # candidates per TR per CG iteration
CONVERGENCE_PATIENCE = 2         # stop after this many non-improving rounds
