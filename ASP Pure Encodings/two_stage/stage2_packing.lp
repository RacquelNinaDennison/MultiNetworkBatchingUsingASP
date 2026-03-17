% define the trips per packing 
trip(F, T, TR, 1..Freq) :- activeRoute(F, T, TR, Freq, _).


&dom { 0..N } = tripLoad(F, T, TR, P, K) :-
    totalLoad(F, T, TR, P, N), trip(F, T, TR, K).


% All units must go across all the trips 
&sum { tripLoad(F, T, TR, P, K) : trip(F, T, TR, K) } = N :-
    totalLoad(F, T, TR, P, N).


% Per-trip capacity: each trip must not exceed transport capacity ──────
&sum { S * tripLoad(F, T, TR, P, K) :
        totalLoad(F, T, TR, P, _), partSize(P, S) } <= C :-
    trip(F, T, TR, K), activeRoute(F, T, TR, _, C).


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


% Priority 2: penalise mono-SKU trips on routes carrying ≥2 part types.
%             The solver will try to mix parts across trips.
:~ tripPartCount(F, T, TR, K, 1),
   routePartTypes(F, T, TR, N), N >= 2.
   [1@2, F, T, TR, K]

% Priority 1: penalise empty trips (wasted dispatches).
:~ trip(F, T, TR, K), tripPartCount(F, T, TR, K, 0).
   [1@1, F, T, TR, K]


#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.
