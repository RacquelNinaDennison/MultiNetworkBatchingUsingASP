% Soft Constraint @3: Value-Weighted Concentration
%
% Same as concentration avoidance, but expensive parts are penalised
% more heavily. The solver spreads high-value parts more aggressively.
%
% Requires: stage2_concentration.lp to be loaded first (defines concentrated/5)
% Metric targeted: R_1 (value-aware)

:~ concentrated(F, T, TR, P, K), partVal(P, V).
   [V@3, F, T, TR, P, K, val]
