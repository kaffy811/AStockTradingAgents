# Phase 6T-N DB Floor

## Summary

- `SELECT 1` p50: `525.73 ms`
- `SELECT 1` p95: `1824.29 ms`
- primary key select p50: `526.59 ms`
- insert + commit p50: `811.43 ms`
- minimum expected create floor: `1863.75 ms`

## Conclusion

The remote database/network floor is already above the steady-state create gate of `300 ms` on the median path.
