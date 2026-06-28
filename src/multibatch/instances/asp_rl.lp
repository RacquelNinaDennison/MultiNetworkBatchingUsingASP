% Locations
location(l1). location(l2). location(l3).
bins(0).
% Parts
part(p1). part(p2).

partTR(p1, tr1). partTR(p1, tr2).
partTR(p2, tr1). partTR(p2, tr2).
% Transports
transportCapacity(tr1, 10).
transportCapacity(tr2, 15).

% Part sizes
partSize(p1, 3).
partSize(p2, 2).

% Demand/Offer: demandOffer(Part, Location, Quantity)
demandOffer(p1, l1, 6).
demandOffer(p2, l1, 4).
demandOffer(p1, l3, -6).
demandOffer(p2, l3, -4).

% Routes: route(From, To, Transport, Distance, Cost)
route(l1, l2, tr1, 3, 9).
route(l1, l2, tr2, 3, 15).
route(l2, l3, tr1, 2, 6).
route(l2, l3, tr2, 2, 10).

% % Domain ranges
% numFlow(0..6).
% numParts(0..6).
% numFreq(0..6).
