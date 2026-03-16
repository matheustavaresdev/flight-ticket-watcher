import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const configId = searchParams.get("configId");
    const origin = searchParams.get("origin");
    const destination = searchParams.get("destination");
    const flightDate = searchParams.get("flightDate");
    const brand = searchParams.get("brand");

    const where: Prisma.PriceSnapshotWhereInput = {};
    if (configId) where.scanRun = { searchConfigId: Number(configId) };
    if (origin) where.origin = origin;
    if (destination) where.destination = destination;
    if (flightDate) where.flightDate = new Date(flightDate);
    if (brand) where.brand = brand;

    const snapshots = await prisma.priceSnapshot.findMany({
      where,
      orderBy: { fetchedAt: "desc" },
      take: 100,
    });
    return NextResponse.json({ data: snapshots });
  } catch {
    return NextResponse.json({ error: "Failed to fetch snapshots" }, { status: 500 });
  }
}
