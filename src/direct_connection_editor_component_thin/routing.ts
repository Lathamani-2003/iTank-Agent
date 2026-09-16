type Point = {
  x: number;
  y: number;
};

type PortSide = "left" | "right" | "top" | "bottom";

type ExistingLine = readonly Point[];

type RouteOptions = {
  padding?: number;
  parallelGap?: number;
  maxShiftAttempts?: number;
  sourceSide?: PortSide;
  targetSide?: PortSide;
};

namespace RTSRouting {
  const EPSILON = 1e-6;

  export const calculateLPath = (
    source: { x: number; y: number; direction: "horizontal" | "vertical" },
    target: { x: number; y: number },
  ): Point[] => {
    const start: Point = { x: Number(source.x), y: Number(source.y) };
    const end: Point = { x: Number(target.x), y: Number(target.y) };

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

  const portVector = (side: PortSide): Point => {
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

  const inferPortSides = (start: Point, end: Point): [PortSide, PortSide] => {
    const dx = end.x - start.x;
    const dy = end.y - start.y;

    if (Math.abs(dx) >= Math.abs(dy)) {
      return dx >= 0 ? ["right", "left"] : ["left", "right"];
    }

    return dy >= 0 ? ["bottom", "top"] : ["top", "bottom"];
  };

  const projectFromPort = (point: Point, side: PortSide, distance: number): Point => {
    const direction = portVector(side);
    return {
      x: point.x + direction.x * distance,
      y: point.y + direction.y * distance,
    };
  };

  const isHorizontal = (a: Point, b: Point): boolean =>
    Math.abs(a.y - b.y) <= EPSILON;

  const isVertical = (a: Point, b: Point): boolean =>
    Math.abs(a.x - b.x) <= EPSILON;

  const isHorizontalSide = (side: PortSide): boolean =>
    side === "left" || side === "right";

  const samePoint = (a: Point, b: Point): boolean =>
    Math.abs(a.x - b.x) <= EPSILON && Math.abs(a.y - b.y) <= EPSILON;

  const intervalOverlap = (
    a1: number,
    a2: number,
    b1: number,
    b2: number,
  ): number => {
    const lo = Math.max(Math.min(a1, a2), Math.min(b1, b2));
    const hi = Math.min(Math.max(a1, a2), Math.max(b1, b2));
    return Math.max(0, hi - lo);
  };

  const pointWithin = (value: number, a: number, b: number): boolean =>
    value >= Math.min(a, b) - EPSILON && value <= Math.max(a, b) + EPSILON;

  const sharesEndpoint = (a: Point, b: Point, c: Point, d: Point): boolean =>
    samePoint(a, c) || samePoint(a, d) || samePoint(b, c) || samePoint(b, d);

  const perpendicularIntersection = (a: Point, b: Point, c: Point, d: Point): boolean => {
    if (isHorizontal(a, b) && isVertical(c, d)) {
      return pointWithin(c.x, a.x, b.x) && pointWithin(a.y, c.y, d.y);
    }

    if (isVertical(a, b) && isHorizontal(c, d)) {
      return pointWithin(a.x, c.x, d.x) && pointWithin(c.y, a.y, b.y);
    }

    return false;
  };

  const parallelOverlapConflict = (
    a: Point,
    b: Point,
    c: Point,
    d: Point,
    gap: number,
  ): boolean => {
    if (isHorizontal(a, b) && isHorizontal(c, d)) {
      return (
        Math.abs(a.y - c.y) < gap - EPSILON &&
        intervalOverlap(a.x, b.x, c.x, d.x) > EPSILON
      );
    }

    if (isVertical(a, b) && isVertical(c, d)) {
      return (
        Math.abs(a.x - c.x) < gap - EPSILON &&
        intervalOverlap(a.y, b.y, c.y, d.y) > EPSILON
      );
    }

    return false;
  };

  const simplifyOrthogonalPath = (input: readonly Point[]): Point[] => {
    const points: Point[] = [];

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

        const redundantHorizontal =
          isHorizontal(previous, current) && isHorizontal(current, next);
        const redundantVertical =
          isVertical(previous, current) && isVertical(current, next);

        if (redundantHorizontal || redundantVertical) {
          points.splice(index, 1);
          changed = true;
          break;
        }
      }
    }

    return points;
  };

  const isStrictlyOrthogonal = (path: readonly Point[]): boolean => {
    if (path.length < 2) return false;

    for (let index = 0; index < path.length - 1; index += 1) {
      const a = path[index];
      const b = path[index + 1];
      if (!isHorizontal(a, b) && !isVertical(a, b)) return false;
    }

    return true;
  };

  const conflictScore = (
    path: readonly Point[],
    existingLines: readonly ExistingLine[],
    parallelGap: number,
  ): number => {
    let score = 0;

    for (let pathIndex = 0; pathIndex < path.length - 1; pathIndex += 1) {
      const a = path[pathIndex];
      const b = path[pathIndex + 1];

      for (const existingLine of existingLines) {
        for (
          let existingIndex = 0;
          existingIndex < existingLine.length - 1;
          existingIndex += 1
        ) {
          const c = existingLine[existingIndex];
          const d = existingLine[existingIndex + 1];

          if (parallelOverlapConflict(a, b, c, d, parallelGap)) {
            score += 100_000;
          }

          if (
            perpendicularIntersection(a, b, c, d) &&
            !sharesEndpoint(a, b, c, d)
          ) {
            score += 10_000;
          }
        }
      }
    }

    return score;
  };

  const manhattanLength = (path: readonly Point[]): number => {
    let length = 0;

    for (let index = 0; index < path.length - 1; index += 1) {
      length +=
        Math.abs(path[index + 1].x - path[index].x) +
        Math.abs(path[index + 1].y - path[index].y);
    }

    return length;
  };

  const shiftedLanes = (
    preferred: number,
    gap: number,
    maxShiftAttempts: number,
  ): number[] => {
    const lanes = [preferred];

    for (let index = 1; index <= maxShiftAttempts; index += 1) {
      const offset = index * gap;
      lanes.push(preferred + offset, preferred - offset);
    }

    return lanes;
  };

  const buildCandidates = (
    start: Point,
    sourceStub: Point,
    targetStub: Point,
    end: Point,
    sourceSide: PortSide,
    targetSide: PortSide,
    parallelGap: number,
    maxShiftAttempts: number,
  ): Point[][] => {
    const sourceHorizontal = isHorizontalSide(sourceSide);
    const targetHorizontal = isHorizontalSide(targetSide);
    const candidates: Point[][] = [];

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

  export const calculateOrthogonalPath = (
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    existingLines: readonly ExistingLine[] = [],
    options: RouteOptions = {},
  ): Point[] => {
    const start = { x: Number(x1), y: Number(y1) };
    const end = { x: Number(x2), y: Number(y2) };

    const padding = Math.max(0, Number(options.padding ?? 20));
    const parallelGap = Math.max(EPSILON, Number(options.parallelGap ?? 12));
    const maxShiftAttempts = Math.max(
      1,
      Math.floor(Number(options.maxShiftAttempts ?? 24)),
    );

    const [inferredSourceSide, inferredTargetSide] = inferPortSides(start, end);
    const sourceSide = options.sourceSide ?? inferredSourceSide;
    const targetSide = options.targetSide ?? inferredTargetSide;

    const sourceStub = projectFromPort(start, sourceSide, padding);
    const targetStub = projectFromPort(end, targetSide, padding);

    const candidates = buildCandidates(
      start,
      sourceStub,
      targetStub,
      end,
      sourceSide,
      targetSide,
      parallelGap,
      maxShiftAttempts,
    )
      .map(simplifyOrthogonalPath)
      .filter(isStrictlyOrthogonal);

    if (!candidates.length) {
      return [start, sourceStub, targetStub, end];
    }

    candidates.sort((first, second) => {
      const firstConflict = conflictScore(first, existingLines, parallelGap);
      const secondConflict = conflictScore(second, existingLines, parallelGap);

      if (firstConflict !== secondConflict) return firstConflict - secondConflict;

      const firstBends = Math.max(0, first.length - 2);
      const secondBends = Math.max(0, second.length - 2);
      if (firstBends !== secondBends) return firstBends - secondBends;

      return manhattanLength(first) - manhattanLength(second);
    });

    return candidates[0];
  };
}

(window as Window & { RTSRouting: typeof RTSRouting }).RTSRouting = RTSRouting;
