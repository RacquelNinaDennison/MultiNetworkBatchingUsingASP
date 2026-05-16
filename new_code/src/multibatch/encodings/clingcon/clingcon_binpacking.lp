bins(1..2).
numParts(0..20).
#const maxFreq = 20.
#const maxItems = 20.

netdemandSupply(Part,Location, Value) :- demandOffer(Part,Location,N), N >= 0, Value = N.
netdemandSupply(Part,Location, Value) :- demandOffer(Part,Location,N), N < 0, Value = N.
netdemandSupply(Part,Location, 0) :- not demandOffer(Part,Location,_), location(Location), part(Part). 

customer(Location,Part) :- netdemandSupply(Part,Location, N), N < 0. 
supplier(Location,Part) :- netdemandSupply(Part,Location, N), N > 0. 

% total demand would be an external variable we define 
% ennumerates to indicate how many parts can be pushed on some link 
% the total flow would be the maximum number of parts that can be pushed on a link, which is the sum of all demands for that part
&dom{ 0..maxFreq } = flow(From,To,P) :-
    route(From,To,_,_,_),
    part(P).

link(From,To) :- route(From,To,_,_,_).
% Customers do not export: flow out of a customer for their demanded part = 0
&sum{flow(From,To,Part)} = 0 :- link(From,To), customer(From, Part).
% Suppliers do not import: flow into a supplier for their supplied part = 0
&sum{flow(From,To,Part)} = 0 :- link(From,To), supplier(To, Part).

&sum{flow(Location,To,Part) : link(Location,To); -1* flow(From,Location,Part) : link(From,Location)} = 
DemandValue :- netdemandSupply(Part,Location,DemandValue). 


% packing definitions 
feasiblePackN(P,TR,0) :- part(P), transportCapacity(TR,_).
feasiblePackN(P,TR,N) :-
    numParts(N), N > 0,
    partSize(P,S),
    transportCapacity(TR,C),
    N * S <= C.

1 { pack(N,P,ID,To,From,TR) : feasiblePackN(P,TR,N) } 1 :-
    route(To,From,TR,_,_),
    bins(ID),
    part(P).

% aggregate bin capacity — total packed weight per bin must not exceed transport capacity
:- #sum {
        N*Size, P :
            pack(N,P,ID,To,From,TR),
            partSize(P,Size)
   } > C,
   transportCapacity(TR,C),
   route(To,From,TR,_,_),
   bins(ID).

&dom{0..maxItems*maxFreq} = auxilary(To,From,TR,ID,Part) :-
    route(To,From,TR,_,_), bins(ID), part(Part).

&dom{ 0..maxFreq } = frequency(To,From,TR,ID) :- route(To,From,TR,_,_), bins(ID).

&sum{ N * frequency(To,From,TR,ID); -auxilary(To,From,TR,ID,P) } = 0 :-
    pack(N,P,ID,To,From,TR),
    route(To,From,TR,_,_),
    N > 0.


&sum{auxilary(To,From,TR,ID,P) } = 0 :-
    pack(0,P,ID,To,From,TR),
    route(To,From,TR,_,_).


&sum{
    auxilary(To,From,TR,ID,Part) : bins(ID), transportCapacity(TR,_), route(To,From,TR,_,_);
    -flow(To,From,Part)
} = 0 :- route(To,From,_,_,_), part(Part).


&minimize{
    Cost * frequency(To,From,TR,I) : route(To,From,TR,D,C), bins(I), Cost = D*C
}.


#show pack/6.
#show. 
&show{flow/3}. 
