#const max_packages = 1.  % number of packing patterns per TR (increase for quality)
#const max_flow = 20.     % maximum flow on any edge
#const max_pack = 20.     % maximum items of one part in a packing

package_id(0..max_packages-1).
numFlow(0..max_flow).
num(0..max_pack).

%%% ============================================================
%%% Flow layer (multi-commodity flow)
%%% ============================================================

% Net supply/demand: 0 if no demandOffer defined
netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D).

% Generate flow variables for each (edge, part) pair
{ flow(From,To,Part,N) : numFlow(N) } :-
    route(From,To,_,_,_),
    part(Part).

% At most one flow value per (From,To,Part) triple
:- flow(From,To,Part,N1), flow(From,To,Part,N2), N1 != N2.

% Flow conservation: outgoing - incoming = netSupplyDemand
:- #sum{ N,To  : flow(Loc,To,Part,N);
        -N,From: flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).


%%% ============================================================
%%% Packing layer (bin packing per transport resource)
%%% ============================================================

% Each (TR, package_id, part) gets a quantity in the packing
1{ pack(N,P,TR,ID) : num(N) } 1 :- transportResource(TR), package_id(ID), part(P).

% Capacity constraint: total size of packing <= TR capacity
:- transportCapacity(TR,Cap),
   package_id(ID),
   #sum{ N*Size,P : pack(N,P,TR,ID), partSize(P,Size) } > Cap.

% Valid TR constraint: a part can only be packed in its valid TRs
:- pack(N,P,TR,ID), N > 0, not partTR(P,TR).


%%% ============================================================
%%% Transport link layer (connecting flow to packings)
%%% ============================================================

{ transportLink(From,To,TR,Freq,ID) : numFlow(Freq) } 1 :-
    route(From,To,TR,_,_),
    package_id(ID).

% At most one frequency per (From,To,TR,ID)
:- transportLink(From,To,TR,Freq1,ID), transportLink(From,To,TR,Freq2,ID), Freq1 != Freq2.

% Linkage: for each edge and part, total transported >= flow
:- flow(From,To,Part,T), T > 0,
   T != #sum{ Q*Freq,TR,ID :
              transportLink(From,To,TR,Freq,ID),
              pack(Q,Part,TR,ID) }.

:- 0 != #sum{ Q*Freq,TR,ID : transportLink(From,To,TR,Freq,ID),
                              pack(Q,Part,TR,ID) },
   not flow(From,To,Part,_),
   location(From),
   location(To),
   part(Part).


%%% ============================================================
%%% Objective: minimize total transport cost
%%% ============================================================

% Note: this only captures operating cost (tr.cost * distance * frequency)
% CO2 and capital costs could be added but require non-integer arithmetic
#minimize { Freq*D*C,From,To,ID,TR :
    transportLink(From,To,TR,Freq,ID),
    route(From,To,TR,D,C)
}.


%%% ============================================================
%%% Show directives
%%% ============================================================

#show flow/4.
#show transportLink/5.
#show pack/4.
