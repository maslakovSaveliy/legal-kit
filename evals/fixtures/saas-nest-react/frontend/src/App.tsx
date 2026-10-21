import { Link, Route, Routes } from 'react-router-dom';
import Register from './pages/Register';
import Pricing from './pages/Pricing';
import Chat from './pages/Chat';
import Footer from './components/Footer';

export default function App() {
  return (
    <>
      <header>
        <Link to="/">Облако</Link> <Link to="/pricing">Тариф</Link> <Link to="/chat">Ассистент</Link>
      </header>
      <Routes>
        <Route path="/" element={<Pricing />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/register" element={<Register />} />
        <Route path="/chat" element={<Chat />} />
      </Routes>
      <Footer />
    </>
  );
}
