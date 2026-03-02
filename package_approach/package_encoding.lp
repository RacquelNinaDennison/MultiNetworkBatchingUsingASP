#const maxPack  = 5.  
#const maxFreq  = 10. 
#const numBins  = 2.   


netsupplydemand(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netsupplydemand(P,L,D) :- demandOffer(P,L,D). 

num(0..maxPack).
bin_id(1..numBins).


{ pack(P, ID, N) : num(N) } = 1 :- part(P), bin_id(ID).
{ assigned(ID, TR) : transportResource(TR) }  :- bin_id(ID).

% Capacity
:- #sum{ N*Size, P : pack(P, ID, N), partSize(P, Size) } > C,
   assigned(ID, TR), transportCapacity(TR, C).

% No empty assigned packages
:- assigned(ID, _),
   #sum{ N, P : pack(P, ID, N) } = 0.

% Symmetry breaking: use lower-numbered bins first
:- bin_id(ID1), bin_id(ID2), ID1 < ID2,
   not assigned(ID1, _), assigned(ID2, _).

active(ID, To, From) :- assigned(ID, TR), route(To, From, TR, _, _).

% How many times do we transport the item within the network?
&dom{ 0..maxFreq } = freq(To, From, TR, ID) 
    :- route(To, From, TR, _, _), assigned(ID, TR), active(ID, To, From).


&dom{ 0..maxFreq*maxPack } = contribution(P, ID, To, From, TR) 
    :- part(P), assigned(ID, TR), route(To, From, TR, _, _), active(ID, To, From).


&sum{ contribution(P, ID, To, From, TR) } = 0 
    :- pack(P, ID, 0), assigned(ID, TR), active(ID, To, From), route(To, From, TR, _, _).

% the total constribution allows us to capture the value of N
&sum{ contribution(P, ID, To, From, TR); -freq(To, From, TR, ID)*N } = 0 
    :- pack(P, ID, N), N > 0, assigned(ID, TR), route(To, From, TR, _, _).


% When the route is assigned, the effective outflow equals the actual contribution.
&sum{ contribution(P, ID, Location, To, TR) } = eff_out(P, ID, Location, To, TR) :- 
    route(Location, To, TR, _, _), 
    assigned(ID, TR), 
    part(P).

% When the route is NOT assigned, the effective outflow is strictly forced to zero.
&sum{ 0 } = eff_out(P, ID, Location, To, TR) :- 
    route(Location, To, TR, _, _), 
    not assigned(ID, TR), 
    bin_id(ID),
    part(P).


&sum{ contribution(P, ID, From, Location, TR) } = eff_in(P, ID, From, Location, TR) :- 
    route(From, Location, TR, _, _), 
    assigned(ID, TR), 
    part(P).


&sum{ 0 } = eff_in(P, ID, From, Location, TR) :- 
    route(From, Location, TR, _, _), 
    not assigned(ID, TR),
    bin_id(ID), 
    part(P).



&sum{ eff_out(P, ID, Location, To, TR) : route(Location, To, TR, _, _),  bin_id(ID)  ;
     -eff_in(P, ID, From, Location, TR) : route(From, Location, TR, _, _),  bin_id(ID) } = Value :- 
    netsupplydemand(P, Location, Value), 
    part(P).


&sum{ freq(To, From, TR, ID) } = 0 :- 
    route(To, From, TR, Distance, Cost), 
    not assigned(ID, TR),
    bin_id(ID).


&minimize{ Distance*Cost * freq(To, From, TR, ID) : route(To, From, TR, Distance, Cost), bin_id(ID) }.

#show pack/3.
#show.
&show{ freq/4 }.