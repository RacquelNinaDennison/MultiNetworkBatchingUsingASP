% ═══════════════════════════════════════════════════════════════════════════
% Stage 2: Per-Trip Bin Packing with Configurable Resilience Objectives
% ═══════════════════════════════════════════════════════════════════════════
%
% Input facts (from Stage 1 via bridging script):
%   totalLoad(From, To, TR, P, N)      — N units of P to ship on this arc
%   activeRoute(From, To, TR, Freq, C) — Freq trips, C = per-trip capacity
%   partSize(P, S)                     — size per unit
%   partVal(P, V)                      — monetary value per unit
%
% Experiment constants:
%   hetero_on       — 1 = penalise mono-part trips, 0 = off
%   concentrated_on — 1 = penalise concentrated trips, 0 = off

#const hetero_on = 1.
#const concentrated_on = 1.


% ── Trip domain ──────────────────────────────────────────────────────────

trip(F, T, TR, 1..Freq) :- activeRoute(F, T, TR, Freq, _).


% ── Decision variables ───────────────────────────────────────────────────

&dom { 0..N } = tripLoad(F, T, TR, P, K) :-
    totalLoad(F, T, TR, P, N), trip(F, T, TR, K).


% ── Auxiliary detection ──────────────────────────────────────────────────

usedTrip(F, T, TR, K) :-
    trip(F, T, TR, K),
    &sum { tripLoad(F, T, TR, P, K) : totalLoad(F, T, TR, P, _) } > 0.

actualFrequency(F, T, TR, Count) :-
    activeRoute(F, T, TR, _, _),
    Count = #count { K : usedTrip(F, T, TR, K) }.

% Symmetry breaking: prevent adjacent trips with identical total volume
:- trip(F, T, TR, K), trip(F, T, TR, K+1),
   &sum { tripLoad(F, T, TR, P, K) : totalLoad(F, T, TR, P, _) ;
         -tripLoad(F, T, TR, P, K+1) : totalLoad(F, T, TR, P, _) } = 0.


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
% Detection Rules (always active — needed for metrics regardless of config)
% ═══════════════════════════════════════════════════════════════════════════

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

% Half-load threshold for concentration detection
halfLoad(F, T, TR, P, N/2) :- totalLoad(F, T, TR, P, N), N > 1.

% Trips exceeding the concentration threshold
concentrated(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } >= H,
    halfLoad(F, T, TR, P, H), trip(F, T, TR, K).

% Mono-part trips on routes with multiple part types
monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.


% ═══════════════════════════════════════════════════════════════════════════
% Soft Constraints (gated by experiment constants)
% ═══════════════════════════════════════════════════════════════════════════

% @2: Heterogeneity — penalise mono-part trips
:~ monoTrip(F, T, TR, K), hetero_on = 1. [1000@2, F, T, TR, K]

% @1: Worst-case exposure — penalise concentrated trips, weighted by part value
:~ concentrated(F, T, TR, P, K), partVal(P, V), concentrated_on = 1.
   [V@1, F, T, TR, P, K, val]


% ═══════════════════════════════════════════════════════════════════════════
% Show directives
% ═══════════════════════════════════════════════════════════════════════════

#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.
#show concentrated/5.
#show monoTrip/4.
#show usedTrip/4.
#show actualFrequency/4.
