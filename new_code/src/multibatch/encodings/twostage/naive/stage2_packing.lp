% input variables from stage 1
% routeFreq(From, To, TR, Freq, TotalCap)
% load(N, P, TR, From, To)

#const hetero_on = 1.
#const concentrated_on = 1.


trip(From, To, TR, 1..Freq) :- routeFreq(From, To, TR, Freq, _).

{tripLoad(F,T,TR,P,Q,K) :Q= 0..N}=1  :- load(N,P,TR,F,T), trip(F,T,TR,K).  

usedTrip(F, T, TR, K) :- tripLoad(F,T,TR,P,N,K) ,  N >0. 

:- #sum{S*N : tripLoad(F,T,TR,P,N,K), partSize(P,S)} > Capacity,
    transportCapacity(TR,Capacity), trip(F,T,TR,K).

:- #sum{Q,K : tripLoad(F,T,TR,P,Q,K)} != N, load(N,P,TR,F,T).

:- #sum{ S*N, P : tripLoad(F,T,TR,P,N,K), partSize(P,S) } > Capacity,
   transportCapacity(TR, Capacity),
   trip(F,T,TR,K).

usedTripCount(F, T, TR, Count) :- routeFreq(F, T, TR, _, _),
    Count = #count { K : usedTrip(F, T, TR, K) }.


% soft constraints 

% halfLoad(F, T, TR, P, N/2) :- load(N,P,TR,F,T), N > 1.

% concentratedLoad(F, T, TR, P, K) :-
%     #sum{Q : tripLoad(F,T,TR,P,Q,K)} >= H,
%     halfLoad(F, T, TR, P, H), trip(F, T, TR, K).


% % mono part check 
% partOnTrip(F, T, TR, K, P) :- tripLoad(F, T, TR, P, Q, K), Q > 0.

% mixedTrip(F, T, TR, K) :- 
%     partOnTrip(F, T, TR, K, P1), 
%     partOnTrip(F, T, TR, K, P2), 
%     P1 != P2.

% monoTripPart(F, T, TR, P) :- 
%     partOnTrip(F, T, TR, K, P), 
%     not mixedTrip(F, T, TR, K).


%:~ concentratedLoad(F, T, TR, P, K), concentrated_on = 1. [weight@1, concentratedLoad, F, T, TR, P, K]
%:~ usedTripCount(F, T, TR, Count). [10000@1, usedTripCount, F, T, TR, Count]
%:~ monoTripPart(F, T, TR, P), hetero_on = 1. [weight@1, monoTripPart, F, T, TR, P]


#minimize { Count, trips, F, T, TR : usedTripCount(F, T, TR, Count) }.