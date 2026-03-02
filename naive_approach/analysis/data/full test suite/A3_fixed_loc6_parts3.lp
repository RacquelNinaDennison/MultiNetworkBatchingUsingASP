% =========================================
% A3_FIXED_LOC_6_PARTS_3
% 6 locations, 3 products, same network
% =========================================

#const maxFlow = 22.
#const maxFreq = 10.
#const maxParts = 5.
#const maxBins = 1.

numFlow(0..maxFlow).
numFreq(0..maxFreq).
numParts(0..maxParts).
bins(0..maxBins).

location(l1). location(l2). location(l3). location(l4). location(l5). location(l6).

part(p1). part(p2). part(p3).
partSize(p1, 2).
partSize(p2, 3).
partSize(p3, 4).

transportCapacity(tr1, 8).
transportCapacity(tr2, 12).

co2price(90).
co2emission(tr1, 30).
co2emission(tr2, 50).

demandOffer(p1, l1, 12).
demandOffer(p1, l5, -5).
demandOffer(p1, l6, -7).

demandOffer(p2, l2, 15).
demandOffer(p2, l5, -9).
demandOffer(p2, l6, -6).

demandOffer(p3, l1, 8).
demandOffer(p3, l2, 6).
demandOffer(p3, l5, -7).
demandOffer(p3, l6, -7).

route(l1,l3,tr1,2,10).
route(l1,l3,tr2,2,14).
route(l2,l3,tr1,2,10).
route(l2,l4,tr2,3,12).
route(l1,l4,tr2,4,16).
route(l3,l5,tr1,2,10).
route(l3,l5,tr2,2,14).
route(l3,l6,tr2,3,12).
route(l4,l5,tr1,2,10).
route(l4,l6,tr2,3,12).
