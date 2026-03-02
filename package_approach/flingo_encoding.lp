#const maxPack  = 5.  
#const maxFreq  = 20. 
#const numBins  = 2.   


netsupplydemand(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netsupplydemand(P,L,D) :- demandOffer(P,L,D). 

num(0..maxPack).
bin_id(1..numBins).


{ pack(P, ID, N) : num(N) } = 1 :- part(P), bin_id(ID).
{ assigned(ID, TR) : transportResource(TR) } 1 :- bin_id(ID).

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
    :- route(To, From, TR, _, _), assigned(ID, TR).



&sum{  N * freq(Location, To, TR, ID)  : route(Location, To, TR, _, _), assigned(ID, TR), pack(P, ID, N);
       -N * freq(From, Location, TR, ID) : route(From, Location, TR, _, _), assigned(ID, TR),pack(P, ID, N)
    } = Value 
    :- netsupplydemand(P, Location, Value), part(P).


route_cost_factor(To, From, TR, Distance*Cost) :- route(To, From, TR, Distance, Cost).

&sum{ DC * freq(To, From, TR, ID) } = route_cost(To, From, TR, ID) :-
    route_cost_factor(To, From, TR, DC),
    assigned(ID, TR).

&sum{ 0 } = route_cost(To, From, TR, ID) :-
    route_cost_factor(To, From, TR, DC),
    not assigned(ID, TR),
    bin_id(ID).


&minimize{ route_cost(To, From, TR, ID) : route(To, From, TR, _, _), bin_id(ID) }.

#show pack/3.
#show assigned/2.
#show.
&show{ freq/4 }.