% Soft Constraint @3: Worst-Case Exposure (concentration avoidance)
%
% No single trip should carry more than half the total allocation of any
% part type on its arc. This sets a floor on R_1 of 0.5.
%
% Metric targeted: R_1

halfLoad(F, T, TR, P, N/2) :- totalLoad(F, T, TR, P, N), N > 1.

concentrated(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > H,
    halfLoad(F, T, TR, P, H), trip(F, T, TR, K).

:~ concentrated(F, T, TR, P, K). [10@3, F, T, TR, P, K]

#show concentrated/5.
