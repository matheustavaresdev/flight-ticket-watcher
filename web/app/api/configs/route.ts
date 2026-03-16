import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const configs = await prisma.searchConfig.findMany({
      orderBy: { createdAt: "desc" },
    });
    return NextResponse.json({ data: configs });
  } catch {
    return NextResponse.json({ error: "Failed to fetch configs" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { origin, destination, mustArriveBy, mustStayUntil, maxTripDays } = body;

    if (!origin || !destination || !mustArriveBy || !mustStayUntil || !maxTripDays) {
      return NextResponse.json(
        { error: "Missing required fields: origin, destination, mustArriveBy, mustStayUntil, maxTripDays" },
        { status: 400 }
      );
    }

    const config = await prisma.searchConfig.create({
      data: {
        origin,
        destination,
        mustArriveBy: new Date(mustArriveBy),
        mustStayUntil: new Date(mustStayUntil),
        maxTripDays,
        minTripDays: body.minTripDays ?? null,
      },
    });
    return NextResponse.json({ data: config }, { status: 201 });
  } catch {
    return NextResponse.json({ error: "Failed to create config" }, { status: 500 });
  }
}
