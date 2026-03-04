% constant values 
package_id(0). 
numFlow(0..20).
num(0..20).



netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D). 

 % flow constaints 
is_consumer(P, L) :- demandOffer(P, L, D), D < 0.
is_producer(P, L) :- demandOffer(P, L, D), D > 0.
1{ flow(From,To,Part,N) : numFlow(N) } 1 :-
    route(From,To,_,_,_), 
    part(Part),
    not is_consumer(Part, From),
    not is_producer(Part, To).


:- flow(From,To,Part,N1), flow(From,To,Part,N2), N1!=N2.


% :- #sum{ N,To  : flow(Loc,To,Part,N);
%         -N,From: flow(From,Loc,Part,N) } != DS,
%    netdemandSupply(Part,Loc,DS).


%%% package encodings 


1{pack(N,P,TR,ID): num(N)} 1:- transportResource(TR), package_id(ID), part(P).

% :- transportCapacity(TR,Cap),
%    package_id(ID),
%    #sum{N*Size,P : pack(N,P,TR,ID), partSize(P,Size)} > Cap.


% can add symmertry breaking here if needed
%% now we can build up the transport links 

1{ transportLink(From,To,TR,Freq,ID) : numFlow(Freq) } :-
    route(From,To,TR,_,_),
    transportResource(TR),
    package_id(ID).

:- transportLink(From,To, TR, Freq1,ID), transportLink(From,To,TR, Freq2,ID), Freq1!=Freq2.
% :- flow(From,To,Part,T),
%    T != #sum { Q*Freq,TR,ID :
%                 transportLink(From,To,TR,Freq,ID),
%                 pack(Q,Part,TR,ID) }.





#minimize { Freq*D*C,From,To,ID,TR :
    transportLink(From,To,TR,Freq,ID),
    route(From,To,TR,D,C)
}.


#show transportLink/5.
#show pack/4.