import 'package:appmetrica_plugin/appmetrica_plugin.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'router.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  await AppMetrica.activate(const AppMetricaConfig('00000000-0000-0000-0000-000000000000'));
  runApp(const ZapisApp());
}

class ZapisApp extends StatelessWidget {
  const ZapisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Запись.Мастер',
      theme: AppTheme.light,
      routerConfig: appRouter,
    );
  }
}
