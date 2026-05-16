#const hetero_on = 1.
#const concentrated_on = 1.



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

% Count distinct parts per trip
tripPartCount(F, T, TR, K, Count) :-
    trip(F, T, TR, K),
    Count = #count { P : tripHasPart(F, T, TR, K, P) }.

% Count distinct part types available on this route
routePartTypes(F, T, TR, Count) :-
    activeRoute(F, T, TR, _, _),
    Count = #count { P : totalLoad(F, T, TR, P, _) }.

% Fair-share threshold: each trip's "fair share" of a part = total / freq
fairShare(F, T, TR, P, N/Freq) :-
    totalLoad(F, T, TR, P, N), activeRoute(F, T, TR, Freq, _), Freq > 0.

% Trip is overloaded for part P if it carries more than the fair share
overloaded(F, T, TR, P, K) :-
    &sum { tripLoad(F, T, TR, P, K) } > Fair,
    fairShare(F, T, TR, P, Fair), trip(F, T, TR, K).

% Mono-part trips on routes with multiple part types
monoTrip(F, T, TR, K) :-
    tripPartCount(F, T, TR, K, 1),
    routePartTypes(F, T, TR, Total), Total > 1.


:~ overloaded(F, T, TR, P, K), partVal(P, V), concentrated_on = 1.
   [V@2, F, T, TR, P, K, overload]
:~ monoTrip(F, T, TR, K), hetero_on = 1. [1@2, F, T, TR, K]
:~ usedTrip(F, T, TR, K). [1@1, F, T, TR, K]

#show.
&show { tripLoad/5 }.
#show tripHasPart/5.
#show tripPartCount/5.
#show routePartTypes/4.
#show concentrated/5.
#show overloaded/5.
#show monoTrip/4.
#show usedTrip/4.
#show actualFrequency/4.
