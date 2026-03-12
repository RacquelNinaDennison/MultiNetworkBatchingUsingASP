#const cap_size_divide = 10000.
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
&dom { N..N } = req(P,L) :- requiredNet(P, L, N).

validFromNode(L) :- demandOffer(_, L, M), M>0.
validToNode(L) :- demandOffer(_, L, M), M<0.
validToNode(L) :- harbor(L).
validFromNode(L) :- harbor(L).

noShipBetweenHarbors(From, To, TR) :- harbor(From), harbor(To), not ship(TR), transportResource(TR).

possibleFlow(From, To, TR, P) :- route(From, To, TR, _,Cost), 
validFromNode(From), validToNode(To),  part(P), 
not noShipBetweenHarbors(From, To, TR).

tRCapSmall(TR,Cap) :- transportCapacity(TR,CapB), Cap=CapB/cap_size_divide.
partSizeSmall(P,S) :- partSize(P,SB), S = SB/cap_size_divide.

&dom { 0..Max } = load(From, To, TR, P) :- possibleFlow(From, To, TR,P), totalSupply(P, Max).
&sum { load(From, L, TR, P): possibleFlow(From, L, TR, P)} = flow_in(P, L) :-  location(L), part(P).
&sum { load(L, To, TR, P): possibleFlow(L, To, TR, P)} = flow_out(P, L) :-  location(L), part(P).
&sum { flow_in(P,L); -1 * flow_out(P,L)} = Net :- requiredNet(P, L, Net).
activeFlow(From,To,TR,P) :-  &sum { load(From, To, TR, P):possibleFlow(From, To, TR, P)} > 0,possibleFlow(From, To, TR, P).

freq(1..max_freq).
1{routeFreq(From, To, TR, Freq, C*Freq) : freq(Freq), tRCapSmall(TR,C) }1 :- activeFlow(From,To,TR,_).

% upper bound
&sum{S*load(F, T, TR, P) : possibleFlow(F, T, TR, P),partSizeSmall(P,S)} <= TotalCap :-
routeFreq(F, T, TR, Freq, TotalCap).
% lower bound
:- &sum{S*load(F, T, TR, P) :possibleFlow(F, T, TR, P),partSizeSmall(P,S)} < Minus1, 
routeFreq(F, T, TR, Freq, TotalCap), tRCapSmall(TR,C), Minus1=TotalCap-C, Freq>1.


% scale_co2 = 1/1000000



% minimsed objective on the co2 emisiions and the distance, this also minimises the costs 
#minimize{D*Freq*E,From,To,TR: routeFreq(From, To, TR, Freq, _),route(From, To, TR,D, _),transportCO2(TR,E);
C*Freq,From,To,TR: routeFreq(From, To, TR, Freq, TotalCap),route(From, To, TR, _, C)}.


% minimise the tied-up capital: opportunity cost of bounded capital during transportation
% compoundInterest(value, time) = value * ((1 + interestRate)^time - 1)
% capitalCost(r) = Σ_B λ_B * compoundInterest(Σ_p α^B_p * value(p), distance(r)/speed(tr(r)))
%
% Since compoundInterest is linear in value, we factor out the compound interest rate per route:
%   CI_factor(r) = ((1 + interestRate)^(distance(r)/speed(tr(r))) - 1)
% and the capital cost becomes:
%   capitalCost(r) = Σ_B λ_B * CI_factor(r) * Σ_p α^B_p * value(p)
%            = Σ_B Σ_p λ_B * CI_factor(r) * α^B_p * value(p)
%
% Since load (α^B_p) is a clingcon constraint variable, we use &minimize

#const interest_rate_percent = 5.
#const interest_scale = 100.

% transit duration for each route: distance / speed (scaled by interest_scale for integer precision)
routeDuration(From, To, TR, D*interest_scale/Speed) :-
    route(From, To, TR, D, _), transportSpeed(TR, Speed), Speed > 0.

% compound interest factor per route, approximated as r * t for integer arithmetic
% CI_factor ≈ interestRate * duration = interest_rate_percent * Dur / interest_scale
% to provide exact compound interest values, override with compoundInterestFactor/3 input facts
% we use taylor expansion to approximate the compound interest factor, as this allows us to maintain linearity in the optimization objective
compoundInterestFactor(From, To, TR, interest_rate_percent * Dur / interest_scale) :-
    routeDuration(From, To, TR, Dur).

% total value loaded per route (clingcon variable): Σ_p load(F,T,TR,P) * value(P)
&sum { V*load(F,T,TR,P) : possibleFlow(F,T,TR,P), partVal(P,V) } = totalLoadValue(F,T,TR) :-
    activeFlow(F,T,TR,_).

% capital cost per route = frequency * CI_factor * totalLoadValue
&sum { CI*Freq*totalLoadValue(F,T,TR) } = capitalCostRoute(F,T,TR) :-
    routeFreq(F,T,TR,Freq,_), compoundInterestFactor(F,T,TR,CI).

% minimise total tied-up capital across all active routes
&minimize { capitalCostRoute(F,T,TR) : activeFlow(F,T,TR,_) }.
