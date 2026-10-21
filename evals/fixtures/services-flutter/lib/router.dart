import 'package:go_router/go_router.dart';

import 'features/booking/booking_page.dart';
import 'features/reviews/reviews_page.dart';
import 'features/settings/settings_page.dart';

final appRouter = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (context, state) => const BookingPage()),
    GoRoute(path: '/reviews', builder: (context, state) => const ReviewsPage()),
    GoRoute(path: '/settings', builder: (context, state) => const SettingsPage()),
  ],
);
