% ═══════════════════════════════════════════════════════════════════════════
% Stage 2: Per-Trip Bin Packing with Resilience Objectives
% ═══════════════════════════════════════════════════════════════════════════
%
% Input facts (from Stage 1 via bridging script):
%   totalLoad(From, To, TR, P, N)      — N units of P to ship on this arc
%   activeRoute(From, To, TR, Freq, C) — Freq trips, C = per-trip capacity
%   partSize(P, S)                     — size per unit
%   partVal(P, V)                      — monetary value per unit
%
% Constraint architecture (layered by priority):
%   @3  Worst-case exposure    — no trip carries > half of any part (R_1 floor)
%   @2  Heterogeneity          — prefer mixed trips over mono-part (A_1)
%   @1  Evenness               — spread each part evenly across trips (R_1 ceiling)
%   @1  Empty trip penalty     — discourage wasted dispatches (cost)
%
% The Stage 1 frequency is an upper bound. Stage 2 may leave trips empty
% if fewer trips suffice — the empty trip penalty at @1 is secondary to
% the resilience objectives at @2 and @3.


% ── Trip domain ────────────────────────────────────────────────────────

trip(F, T, TR, 1..Freq) :- activeRoute(F, T, TR, Freq, _).


% ── Decision variables ─────────────────────────────────────────────────

&dom { 0..N } = tripLoad(F, T, TR, P, K) :-
    totalLoad(F, T, TR, P, N), trip(F, T, TR, K).


% ═══════════════════════════════════════════════════════════════════════════
% Hard Constraints
% ═══════════════════════════════════════════════════════════════════════════

% Load conservation: all units must be assigned across trips
&sum { tripLoad(F, T, TR, P, K) : trip(F, T, TR, K) } = N :-
    totalLoad(F, T, TR, P, N).

% Per-trip capacity: each trip must not exceed transport capacity
&sum { S * tripLoad(F, T, TR, P, K) :
        totalLoad(F, T, TR, P, _), partSize(P, S) } <= C :-
    trip(F, T, TR, K), activeRoute(F, T, TR, _, C).


% ═══════════════════════════════════════════════════════════════════════════
% Detection Atoms
% ═══════════════════════════════════════════════════════════════════════════

% Which parts are present on each trip (non-zero assignment)
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


% ═══════════════════════════════════════════════════════════════════════════
% Soft Constraint @3: Worst-Case Exposure (concentration avoidance)
% ═══════════════════════════════════════════════════════════════════════════
%
% No single trip should carry more than half the total allocation of any
% part type on its arc. Exceeding this means losing one trip wipes out a
% majority of a part's supply — the primary driver of cascading failures.
%
% This sets a floor on R_1 of 0.5.
%
% Metric targeted: R_1

% Half-load threshold
halfLoad(F, T, TR, P, N/2) :- totalLoad(F, T, TR, P, N), N > 1.

% Detect trips exceeding the concentration threshold
concentrated(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > H,
    halfLoad(F, T, TR, P, H), trip(F, T, TR, K).

% Penalise concentrated packings (highest priority)
:~ concentrated(F, T, TR, P, K). [10@3, F, T, TR, P, K]

% Value-weighted variant: expensive parts penalised more heavily
:~ concentrated(F, T, TR, P, K), partVal(P, V).
   [V@3, F, T, TR, P, K, val]


% ═══════════════════════════════════════════════════════════════════════════
% Soft Constraint @2: Heterogeneity (mono-part avoidance)
% ═══════════════════════════════════════════════════════════════════════════
%
% Each trip should carry multiple part types rather than being mono-part.
% A mixed trip has immediate assembly utility at the destination; a
% mono-part trip only becomes useful when the "matching" shipment arrives.
%
% Only penalises mono-part trips on routes that ship multiple part types.
%
% Metric targeted: A_1

monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.

:~ monoTrip(F, T, TR, K). [5@2, F, T, TR, K]


% ═══════════════════════════════════════════════════════════════════════════
% Soft Constraint @1: Evenness (load balance)
% ═══════════════════════════════════════════════════════════════════════════
%
% For N units of part P across Freq trips, the ideal maximum per trip is
% ceil(N/Freq). Trips exceeding this are penalised. Perfect evenness
% pushes R_1 toward 1 - 1/Freq.
%
% Metric targeted: R_1 (refines beyond the @3 floor)

% Compute ideal maximum per trip (ceiling of N/Freq)
idealMax(F, T, TR, P, (N + Freq - 1) / Freq) :-
    totalLoad(F, T, TR, P, N),
    activeRoute(F, T, TR, Freq, _).

% Detect trips exceeding the ideal maximum
overloaded(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > Max,
    idealMax(F, T, TR, P, Max), trip(F, T, TR, K).

:~ overloaded(F, T, TR, P, K). [1@1, F, T, TR, P, K]


% ═══════════════════════════════════════════════════════════════════════════
% Soft Constraint @1: Empty Trip Penalty
% ═══════════════════════════════════════════════════════════════════════════
%
% Penalise trips that carry nothing. Stage 1's frequency is an upper
% bound — if Stage 2 can pack everything into fewer trips, the unused
% trips are wasted dispatches. However this is at @1, so it is secondary
% to resilience objectives: the solver will prefer using more trips for
% diversification over saving dispatch costs.

:~ trip(F, T, TR, K), tripPartCount(F, T, TR, K, 0).
   [1@1, F, T, TR, K, empty]


#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.
#show concentrated/5.
#show monoTrip/4.
#show overloaded/5.
