% Weighted variant of stage_2_packing.lp for resilience weight-tuning.
%
% The original encoding is LEXICOGRAPHIC: resilience penalties live at level @2
% and dominate trip-count at @1 ("resilience at any trip cost"), giving a single
% operating point. This variant puts everything on a SINGLE level @1 with tunable
% integer weights, so sweeping w_hetero / w_conc traces the resilience<->cost
% trade-off curve.
%
%   w_hetero = 0, w_conc = 0  -> baseline (cost only)
%   w_hetero > 0              -> penalise mono-part trips (heterogeneity)
%   w_conc   > 0              -> penalise over-fair-share trips (anti-concentration)
%
% NB: overload is penalised by COUNT here (not value-weighted as in the original
% [V@2]) so the weights are comparable to trip-count and integer-tunable. Counts
% (monoTrip/overloaded) are still derived and shown for extraction regardless of
% weight, so mono_count / concentrated_count remain correct.

#const w_hetero = 1.
#const w_conc = 1.

trip(F, T, TR, 1..Freq) :- activeRoute(F, T, TR, Freq, _).

&dom { 0..N } = tripLoad(F, T, TR, P, K) :-
    totalLoad(F, T, TR, P, N), trip(F, T, TR, K).

usedTrip(F, T, TR, K) :-
    trip(F, T, TR, K),
    &sum { tripLoad(F, T, TR, P, K) : totalLoad(F, T, TR, P, _) } > 0.

actualFrequency(F, T, TR, Count) :-
    activeRoute(F, T, TR, _, _),
    Count = #count { K : usedTrip(F, T, TR, K) }.

&sum { tripLoad(F, T, TR, P, K) : trip(F, T, TR, K) } = N :-
    totalLoad(F, T, TR, P, N).

% Per-trip capacity: each trip must not exceed transport capacity
&sum { S * tripLoad(F, T, TR, P, K) :
        totalLoad(F, T, TR, P, _), partSize(P, S) } <= C :-
    trip(F, T, TR, K), activeRoute(F, T, TR, _, C).

tripHasPart(F, T, TR, K, P) :-
    &sum { tripLoad(F, T, TR, P, K) :
            totalLoad(F, T, TR, P, _), trip(F, T, TR, K) } > 0,
    totalLoad(F, T, TR, P, _), trip(F, T, TR, K).

tripPartCount(F, T, TR, K, Count) :-
    trip(F, T, TR, K),
    Count = #count { P : tripHasPart(F, T, TR, K, P) }.

routePartTypes(F, T, TR, Count) :-
    activeRoute(F, T, TR, _, _),
    Count = #count { P : totalLoad(F, T, TR, P, _) }.

fairShare(F, T, TR, P, N/Freq) :-
    totalLoad(F, T, TR, P, N), activeRoute(F, T, TR, Freq, _), Freq > 0.

overloaded(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > Fair,
    fairShare(F, T, TR, P, Fair), trip(F, T, TR, K).

monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.

% Single weighted objective (all at level @1):
:~ usedTrip(F, T, TR, K).                  [1@1, used, F, T, TR, K]
:~ monoTrip(F, T, TR, K).                  [w_hetero@1, mono, F, T, TR, K]
:~ overloaded(F, T, TR, P, K).             [w_conc@1, over, F, T, TR, P, K]

#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.
#show overloaded/5.
#show monoTrip/4.
#show usedTrip/4.
#show actualFrequency/4.
