import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const config = await prisma.searchConfig.findUnique({
      where: { id: Number(id) },
      include: {
        _count: { select: { scanRuns: true } },
        priceAlerts: { orderBy: { createdAt: "desc" }, take: 1 },
      },
    });
    if (!config) {
      return NextResponse.json({ error: "Config not found" }, { status: 404 });
    }
    return NextResponse.json({ data: config });
  } catch {
    return NextResponse.json({ error: "Failed to fetch config" }, { status: 500 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { origin, destination, mustArriveBy, mustStayUntil, maxTripDays } = body;

    if (!origin || !destination || !mustArriveBy || !mustStayUntil || !maxTripDays) {
      return NextResponse.json(
        { error: "Missing required fields: origin, destination, mustArriveBy, mustStayUntil, maxTripDays" },
        { status: 400 }
      );
    }

    const config = await prisma.searchConfig.update({
      where: { id: Number(id) },
      data: {
        origin,
        destination,
        mustArriveBy: new Date(mustArriveBy),
        mustStayUntil: new Date(mustStayUntil),
        maxTripDays,
        minTripDays: body.minTripDays ?? null,
      },
    });
    return NextResponse.json({ data: config });
  } catch {
    return NextResponse.json({ error: "Failed to update config" }, { status: 500 });
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    await prisma.searchConfig.delete({ where: { id: Number(id) } });
    return new NextResponse(null, { status: 204 });
  } catch {
    return NextResponse.json({ error: "Failed to delete config" }, { status: 500 });
  }
}
