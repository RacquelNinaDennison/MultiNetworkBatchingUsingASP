#const cap_size_divide = 1.
#const max_freq = 30.

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0) :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).


validFromNode(L) :- demandOffer(_, L, M), M>0.
validToNode(L) :- demandOffer(_, L, M), M<0.
%validToNode(L) :- harbor(L).
%validFromNode(L) :- harbor(L).

%noShipBetweenHarbors(From, To, TR) :- harbor(From), harbor(To), not ship(TR), transportResource(TR).

possibleFlow(From, To, TR, P) :- route(From, To, TR, _,Cost), 
validFromNode(From), validToNode(To),  part(P).

tRCapSmall(TR,Cap) :- transportCapacity(TR,CapB), Cap=CapB/cap_size_divide.
partSizeSmall(P,S) :- partSize(P,SB), S = SB/cap_size_divide.


&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max).
&sum { load(From, L, TR, P): possibleFlow(From, L, TR, P)} = flow_in(P, L) :-  location(L), part(P).
&sum { load(L, To, TR, P): possibleFlow(L, To, TR, P)} = flow_out(P, L) :-  location(L), part(P).
&sum { flow_in(P,L); -1 * flow_out(P,L)} = Net :- requiredNet(P, L, Net).
activeFlow(From,To,TR,P) :-  &sum { load(From, To, TR, P):possibleFlow(From, To, TR, P)} > 0,possibleFlow(From, To, TR, P).

% this can be based on the number of items within the network which can be transported 

freq(1..max_freq).
1{routeFreq(From, To, TR, Freq, C*Freq) : freq(Freq), tRCapSmall(TR,C) }1 :- activeFlow(From,To,TR,_).

% upper bound
&sum{S*load(F, T, TR, P) : possibleFlow(F, T, TR, P),partSizeSmall(P,S)} <= TotalCap :-
routeFreq(F, T, TR, Freq, TotalCap).
% lower bound
:- &sum{S*load(F, T, TR, P) :possibleFlow(F, T, TR, P),partSizeSmall(P,S)} < Minus1, 
routeFreq(F, T, TR, Freq, TotalCap), tRCapSmall(TR,C), Minus1=TotalCap-C, Freq>1.


% scale_co2 = 1/1000000

% modelling disrupted routes in the network 

% minimsed objective on the co2 emisiions and the distance, this also minimises the costs 
#minimize{D*Freq*E,From,To,TR: routeFreq(From, To, TR, Freq, _),route(From, To, TR,D, _),transportCO2(TR,E);
C*Freq,From,To,TR: routeFreq(From, To, TR, Freq, TotalCap),route(From, To, TR, _, C)}.

#show. 
&show{requiredNet/3}.
&show{hasDemand/2}.
&show{hasOffer/2}.