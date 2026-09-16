"use strict";
var RTSRouting;
(function (RTSRouting) {
    const EPSILON = 1e-6;
    RTSRouting.calculateLPath = (source, target) => {
        const start = { x: Number(source.x), y: Number(source.y) };
        const end = { x: Number(target.x), y: Number(target.y) };
        if (start.x === end.x || start.y === end.y) {
            return [start, end];
        }
        if (source.direction === "horizontal") {
            return [
                start,
                { x: end.x, y: start.y },
                end,
            ];
        }
        return [
            start,
            { x: start.x, y: end.y },
            end,
        ];
    };
    const portVector = (side) => {
        switch (side) {
            case "left":
                return { x: -1, y: 0 };
            case "right":
                return { x: 1, y: 0 };
            case "top":
                return { x: 0, y: -1 };
            case "bottom":
                return { x: 0, y: 1 };
        }
    };
    const inferPortSides = (start, end) => {
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        if (Math.abs(dx) >= Math.abs(dy)) {
            return dx >= 0 ? ["right", "left"] : ["left", "right"];
        }
        return dy >= 0 ? ["bottom", "top"] : ["top", "bottom"];
    };
    const projectFromPort = (point, side, distance) => {
        const direction = portVector(side);
        return {
            x: point.x + direction.x * distance,
            y: point.y + direction.y * distance,
        };
    };
    const isHorizontal = (a, b) => Math.abs(a.y - b.y) <= EPSILON;
    const isVertical = (a, b) => Math.abs(a.x - b.x) <= EPSILON;
    const isHorizontalSide = (side) => side === "left" || side === "right";
    const samePoint = (a, b) => Math.abs(a.x - b.x) <= EPSILON && Math.abs(a.y - b.y) <= EPSILON;
    const intervalOverlap = (a1, a2, b1, b2) => {
        const lo = Math.max(Math.min(a1, a2), Math.min(b1, b2));
        const hi = Math.min(Math.max(a1, a2), Math.max(b1, b2));
        return Math.max(0, hi - lo);
    };
    const pointWithin = (value, a, b) => value >= Math.min(a, b) - EPSILON && value <= Math.max(a, b) + EPSILON;
    const sharesEndpoint = (a, b, c, d) => samePoint(a, c) || samePoint(a, d) || samePoint(b, c) || samePoint(b, d);
    const perpendicularIntersection = (a, b, c, d) => {
        if (isHorizontal(a, b) && isVertical(c, d)) {
            return pointWithin(c.x, a.x, b.x) && pointWithin(a.y, c.y, d.y);
        }
        if (isVertical(a, b) && isHorizontal(c, d)) {
            return pointWithin(a.x, c.x, d.x) && pointWithin(c.y, a.y, b.y);
        }
        return false;
    };
    const parallelOverlapConflict = (a, b, c, d, gap) => {
        if (isHorizontal(a, b) && isHorizontal(c, d)) {
            return (Math.abs(a.y - c.y) < gap - EPSILON &&
                intervalOverlap(a.x, b.x, c.x, d.x) > EPSILON);
        }
        if (isVertical(a, b) && isVertical(c, d)) {
            return (Math.abs(a.x - c.x) < gap - EPSILON &&
                intervalOverlap(a.y, b.y, c.y, d.y) > EPSILON);
        }
        return false;
    };
    const simplifyOrthogonalPath = (input) => {
        const points = [];
        for (const point of input) {
            const normalized = { x: Number(point.x), y: Number(point.y) };
            if (!points.length || !samePoint(points[points.length - 1], normalized)) {
                points.push(normalized);
            }
        }
        let changed = true;
        while (changed && points.length >= 3) {
            changed = false;
            for (let index = 1; index < points.length - 1; index += 1) {
                const previous = points[index - 1];
                const current = points[index];
                const next = points[index + 1];
                const redundantHorizontal = isHorizontal(previous, current) && isHorizontal(current, next);
                const redundantVertical = isVertical(previous, current) && isVertical(current, next);
                if (redundantHorizontal || redundantVertical) {
                    points.splice(index, 1);
                    changed = true;
                    break;
                }
            }
        }
        return points;
    };
    const isStrictlyOrthogonal = (path) => {
        if (path.length < 2)
            return false;
        for (let index = 0; index < path.length - 1; index += 1) {
            const a = path[index];
            const b = path[index + 1];
            if (!isHorizontal(a, b) && !isVertical(a, b))
                return false;
        }
        return true;
    };
    const conflictScore = (path, existingLines, parallelGap) => {
        let score = 0;
        for (let pathIndex = 0; pathIndex < path.length - 1; pathIndex += 1) {
            const a = path[pathIndex];
            const b = path[pathIndex + 1];
            for (const existingLine of existingLines) {
                for (let existingIndex = 0; existingIndex < existingLine.length - 1; existingIndex += 1) {
                    const c = existingLine[existingIndex];
                    const d = existingLine[existingIndex + 1];
                    if (parallelOverlapConflict(a, b, c, d, parallelGap)) {
                        score += 100000;
                    }
                    if (perpendicularIntersection(a, b, c, d) &&
                        !sharesEndpoint(a, b, c, d)) {
                        score += 10000;
                    }
                }
            }
        }
        return score;
    };
    const manhattanLength = (path) => {
        let length = 0;
        for (let index = 0; index < path.length - 1; index += 1) {
            length +=
                Math.abs(path[index + 1].x - path[index].x) +
                    Math.abs(path[index + 1].y - path[index].y);
        }
        return length;
    };
    const shiftedLanes = (preferred, gap, maxShiftAttempts) => {
        const lanes = [preferred];
        for (let index = 1; index <= maxShiftAttempts; index += 1) {
            const offset = index * gap;
            lanes.push(preferred + offset, preferred - offset);
        }
        return lanes;
    };
    const buildCandidates = (start, sourceStub, targetStub, end, sourceSide, targetSide, parallelGap, maxShiftAttempts) => {
        const sourceHorizontal = isHorizontalSide(sourceSide);
        const targetHorizontal = isHorizontalSide(targetSide);
        const candidates = [];
        if (sourceHorizontal && targetHorizontal) {
            const preferredY = (sourceStub.y + targetStub.y) / 2;
            for (const laneY of shiftedLanes(preferredY, parallelGap, maxShiftAttempts)) {
                candidates.push([
                    start,
                    sourceStub,
                    { x: sourceStub.x, y: laneY },
                    { x: targetStub.x, y: laneY },
                    targetStub,
                    end,
                ]);
            }
            return candidates;
        }
        if (!sourceHorizontal && !targetHorizontal) {
            const preferredX = (sourceStub.x + targetStub.x) / 2;
            for (const laneX of shiftedLanes(preferredX, parallelGap, maxShiftAttempts)) {
                candidates.push([
                    start,
                    sourceStub,
                    { x: laneX, y: sourceStub.y },
                    { x: laneX, y: targetStub.y },
                    targetStub,
                    end,
                ]);
            }
            return candidates;
        }
        if (sourceHorizontal) {
            // Source exits horizontally; target enters vertically.
            const preferredY = targetStub.y;
            for (const laneY of shiftedLanes(preferredY, parallelGap, maxShiftAttempts)) {
                candidates.push([
                    start,
                    sourceStub,
                    { x: sourceStub.x, y: laneY },
                    { x: targetStub.x, y: laneY },
                    targetStub,
                    end,
                ]);
            }
            return candidates;
        }
        // Source exits vertically; target enters horizontally.
        const preferredX = targetStub.x;
        for (const laneX of shiftedLanes(preferredX, parallelGap, maxShiftAttempts)) {
            candidates.push([
                start,
                sourceStub,
                { x: laneX, y: sourceStub.y },
                { x: laneX, y: targetStub.y },
                targetStub,
                end,
            ]);
        }
        return candidates;
    };
    RTSRouting.calculateOrthogonalPath = (x1, y1, x2, y2, existingLines = [], options = {}) => {
        var _a, _b, _c, _d, _e;
        const start = { x: Number(x1), y: Number(y1) };
        const end = { x: Number(x2), y: Number(y2) };
        const padding = Math.max(0, Number((_a = options.padding) !== null && _a !== void 0 ? _a : 20));
        const parallelGap = Math.max(EPSILON, Number((_b = options.parallelGap) !== null && _b !== void 0 ? _b : 12));
        const maxShiftAttempts = Math.max(1, Math.floor(Number((_c = options.maxShiftAttempts) !== null && _c !== void 0 ? _c : 24)));
        const [inferredSourceSide, inferredTargetSide] = inferPortSides(start, end);
        const sourceSide = (_d = options.sourceSide) !== null && _d !== void 0 ? _d : inferredSourceSide;
        const targetSide = (_e = options.targetSide) !== null && _e !== void 0 ? _e : inferredTargetSide;
        const sourceStub = projectFromPort(start, sourceSide, padding);
        const targetStub = projectFromPort(end, targetSide, padding);
        const candidates = buildCandidates(start, sourceStub, targetStub, end, sourceSide, targetSide, parallelGap, maxShiftAttempts)
            .map(simplifyOrthogonalPath)
            .filter(isStrictlyOrthogonal);
        if (!candidates.length) {
            return [start, sourceStub, targetStub, end];
        }
        candidates.sort((first, second) => {
            const firstConflict = conflictScore(first, existingLines, parallelGap);
            const secondConflict = conflictScore(second, existingLines, parallelGap);
            if (firstConflict !== secondConflict)
                return firstConflict - secondConflict;
            const firstBends = Math.max(0, first.length - 2);
            const secondBends = Math.max(0, second.length - 2);
            if (firstBends !== secondBends)
                return firstBends - secondBends;
            return manhattanLength(first) - manhattanLength(second);
        });
        return candidates[0];
    };
})(RTSRouting || (RTSRouting = {}));
window.RTSRouting = RTSRouting;
