% Soft Constraint @1: Evenness (load balance)
%
% For N units of part P across Freq trips, the ideal maximum per trip is
% ceil(N/Freq). Trips exceeding this are penalised. Perfect evenness
% pushes R_1 toward 1 - 1/Freq.
%
% Metric targeted: R_1 (refines beyond the @3 floor)

idealMax(F, T, TR, P, (N + Freq - 1) / Freq) :-
    totalLoad(F, T, TR, P, N),
    activeRoute(F, T, TR, Freq, _).

overloaded(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > Max,
    idealMax(F, T, TR, P, Max), trip(F, T, TR, K).

:~ overloaded(F, T, TR, P, K). [1@1, F, T, TR, P, K]

#show overloaded/5.
