% Domains
&dom{ 0..maxFreq } = flow(From,To,P) :- link(From,To), part(P).
&dom{ 0..maxFreq } = frequency(From,To,TR,ID) :- route(From,To,TR,_,_), bins(ID).
&dom{ 0..maxItems*maxFreq } = aux(From,To,TR,ID,P) :- route(From,To,TR,_,_), bins(ID), part(P).

% Flow conservation (handles suppliers, customers, and transit nodes)
link(From,To) :- route(From,To,_,_,_).

&sum{ flow(Loc,To,P) : link(Loc,To);
     -flow(From,Loc,P) : link(From,Loc) } = DS :-
    netdemandSupply(P,Loc,DS).

% Packing choices (consistent argument order!)
{ pack(N,P,ID,From,To,TR) : feasiblePackN(P,TR,N) } = 1 :-
    route(From,To,TR,_,_), bins(ID), part(P).

% Auxiliary linearization: aux = N * frequency when pack(N,...) holds
&sum{ N * frequency(From,To,TR,ID); -aux(From,To,TR,ID,P) } = 0 :-
    pack(N,P,ID,From,To,TR), N > 0.

&sum{ aux(From,To,TR,ID,P) } = 0 :-
    pack(0,P,ID,From,To,TR).

% Flow linking: total dispatched across all bins/TRs = flow on each link
&sum{ aux(From,To,TR,ID,P) : bins(ID), route(From,To,TR,_,_);
     -flow(From,To,P) } = 0 :-
    link(From,To), part(P).

% Objective
&minimize{ Cost * frequency(From,To,TR,ID) :
    route(From,To,TR,D,C), bins(ID), Cost = D*C }.