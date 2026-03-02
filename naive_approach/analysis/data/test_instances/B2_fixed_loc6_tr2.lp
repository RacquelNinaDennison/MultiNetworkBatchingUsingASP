% =========================================
% B2_FIXED_LOC_6_TR_2
% 6 locations, 2 products, 2 transport resources
% =========================================

#const maxFlow = 18.
#const maxFreq = 8.
#const maxParts = 5.
#const maxBins = 1.

numFlow(0..maxFlow).
numFreq(0..maxFreq).
numParts(0..maxParts).
bins(0..maxBins).

location(l1). location(l2). location(l3). location(l4). location(l5). location(l6).

part(p1). part(p2).
partSize(p1, 2).
partSize(p2, 3).

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
