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
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const { origin, destination, mustArriveBy, mustStayUntil, maxTripDays } = body;

    if (!origin || !destination || !mustArriveBy || !mustStayUntil || !maxTripDays) {
      return NextResponse.json(
        { error: "Missing required fields: origin, destination, mustArriveBy, mustStayUntil, maxTripDays" },
        { status: 400 }
      );
    }

    const parsedMaxTripDays = parseInt(String(maxTripDays), 10);
    const parsedMinTripDays = body.minTripDays != null ? parseInt(String(body.minTripDays), 10) : null;

    if (Number.isNaN(parsedMaxTripDays)) {
      return NextResponse.json({ error: "maxTripDays must be a number" }, { status: 400 });
    }
    if (parsedMinTripDays !== null && Number.isNaN(parsedMinTripDays)) {
      return NextResponse.json({ error: "minTripDays must be a number" }, { status: 400 });
    }

    const arriveByDate = new Date(String(mustArriveBy));
    const stayUntilDate = new Date(String(mustStayUntil));

    if (isNaN(arriveByDate.getTime())) {
      return NextResponse.json({ error: "mustArriveBy must be a valid date" }, { status: 400 });
    }
    if (isNaN(stayUntilDate.getTime())) {
      return NextResponse.json({ error: "mustStayUntil must be a valid date" }, { status: 400 });
    }
    if (stayUntilDate < arriveByDate) {
      return NextResponse.json({ error: "mustStayUntil must be >= mustArriveBy" }, { status: 400 });
    }
    if (parsedMaxTripDays < 1) {
      return NextResponse.json({ error: "maxTripDays must be >= 1" }, { status: 400 });
    }

    const config = await prisma.searchConfig.create({
      data: {
        origin: String(origin),
        destination: String(destination),
        mustArriveBy: arriveByDate,
        mustStayUntil: stayUntilDate,
        maxTripDays: parsedMaxTripDays,
        minTripDays: parsedMinTripDays,
      },
    });
    return NextResponse.json({ data: config }, { status: 201 });
  } catch {
    return NextResponse.json({ error: "Failed to create config" }, { status: 500 });
  }
}
