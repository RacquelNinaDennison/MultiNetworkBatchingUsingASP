% ═══════════════════════════════════════════════════════════════════════════
% Stage 2 BASE: Per-Trip Bin Packing 
% ═══════════════════════════════════════════════════════════════════════════
%
% This file contains the structural constraints shared by ALL Stage 2
% configurations.  Objectives and diversification rules are injected by
% the benchmark runner as extra rules on top of this base.
%
% Input facts (from run_two_stage.py / quality_benchmark.py):
%   totalLoad(From, To, TR, P, N)       — N units of P to ship on this arc
%   activeRoute(From, To, TR, Freq, C)  — Freq trips, C = per-trip capacity
%   partSize(P, S)                      — raw (unscaled) size per unit
%   partVal(P, V)                       — monetary value per unit (for holding cost)
%   transitTime(F, T, TR, T)            — scaled transit duration (for holding cost)


% ── Trip domain ──────────────────────────────────────────────────────────

trip(F, T, TR, 1..Freq) :- activeRoute(F, T, TR, Freq, _).


% ── Decision variables ───────────────────────────────────────────────────

&dom { 0..N } = tripLoad(F, T, TR, P, K) :-
    totalLoad(F, T, TR, P, N), trip(F, T, TR, K).


% All the trip loads should sum up to the total load for this arc and part.

&sum { tripLoad(F, T, TR, P, K) : trip(F, T, TR, K) } = N :-
    totalLoad(F, T, TR, P, N).


% Per-trip capacity: each trip must not exceed transport capacity.

&sum { S * tripLoad(F, T, TR, P, K) :
        totalLoad(F, T, TR, P, _), partSize(P, S) } <= C :-
    trip(F, T, TR, K), activeRoute(F, T, TR, _, C).



tripHasPart(F, T, TR, K, P) :-
    &sum { tripLoad(F, T, TR, P, K) :
            totalLoad(F, T, TR, P, _), trip(F, T, TR, K) } > 0,
    totalLoad(F, T, TR, P, _), trip(F, T, TR, K).

% Count distinct parts per trip
tripPartCount(F, T, TR, K, Count) :-
    trip(F, T, TR, K),
    Count = #count { P : tripHasPart(F, T, TR, K, P) }.

% Count distinct part types available on this route
routePartTypes(F, T, TR, Count) :-
    activeRoute(F, T, TR, _, _),
    Count = #count { P : totalLoad(F, T, TR, P, _) }.


% Prefer even distribution across trips — directly improves R_TR
halfLoad(F, T, TR, P, N/2) :- totalLoad(F, T, TR, P, N), N > 1.

concentrated(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > H,
    halfLoad(F, T, TR, P, H), trip(F, T, TR, K).

:~ concentrated(F, T, TR, P, K). [10@3, F, T, TR, P, K]

% Hard: no single trip carries more than half the total arc load for a part
% This directly prevents R_1 = 0 by construction
:- halfLoad(F, T, TR, P, H),
   H > 0,
   trip(F, T, TR, K),
   &sum { tripLoad(F, T, TR, P, K) } > H.

   
#show concentrated/5.


#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.

