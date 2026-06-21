import { create } from 'zustand';

const useClaimStore = create((set) => ({
  claims: [],
  totalClaims: 0,
  currentClaim: null,
  filters: {
    status: 'escalated', // 'escalated', 'pending_clarification', 'all', 'resolved'
    fraud_score_min: null,
    fraud_score_max: null,
  },
  
  setClaims: (claims, total) => set({ claims, totalClaims: total }),
  setCurrentClaim: (claim) => set({ currentClaim: claim }),
  setFilter: (key, value) => set((state) => ({
    filters: { ...state.filters, [key]: value }
  })),
  clearFilters: () => set({
    filters: {
      status: 'escalated',
      fraud_score_min: null,
      fraud_score_max: null,
    }
  })
}));

export default useClaimStore;
